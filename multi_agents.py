import os
from datetime import datetime
from typing import TypedDict
from langgraph.graph import StateGraph, END
from huggingface_hub import InferenceClient
from ddgs import DDGS
from pymongo import MongoClient

# --- 1. Database Setup ---
client = MongoClient("mongodb://mongodb:27017/")
collection = client["research_swarm"]["knowledge_base"]

# --- 2. AI Model Setup ---
llm_client = InferenceClient(
    model="Qwen/Qwen2.5-Coder-32B-Instruct",
    token=os.environ.get("HF_TOKEN")
)

def ask_llm(prompt: str) -> str:
    """Helper function to format the prompt as a proper chat conversation."""
    messages = [{"role": "user", "content": prompt}]
    response = llm_client.chat_completion(
        messages=messages, 
        max_tokens=1024, 
        temperature=0.3
    )
    return response.choices[0].message.content

# --- 3. Define the State (The Shared Memory) ---
class AgentState(TypedDict):
    topic: str
    raw_research: str
    draft_report: str
    feedback: str
    status: str  
    revision_count: int

# --- 4. Define the Nodes (The Agents) ---

def searcher_node(state: AgentState):
    print("\n🔍 SEARCHER: Gathering today's news...")
    query = state["topic"]
    if state["feedback"]:
        print(f"   -> Adjusting search based on feedback: {state['feedback']}")
        query = f"{state['topic']} {state['feedback']}"

    try:
        results = DDGS().news(query, timelimit="d", max_results=5)
        
        if not results:
            print("   -> No news found. Falling back to general web search...")
            results = DDGS().text(query, timelimit="d", max_results=5)
            
        snippets = "\n".join([f"- [{r.get('date', 'Recent')}] {r.get('title', '')}: {r.get('body', '')}" for r in results])
    except Exception as e:
        print(f"   -> Search API Error: {e}")
        snippets = "The search engine blocked the request or returned no data for today. Please inform the user that live data is currently unavailable."
        
    new_research = state["raw_research"] + "\n" + snippets
    return {"raw_research": new_research}

def analyst_node(state: AgentState):
    print("\n✍️ ANALYST: Writing the report...")
    today = datetime.now().strftime("%A, %B %d, %Y")
    
    prompt = f"""
    You are an expert Financial Analyst. Today is {today}. 
    Write a 3-paragraph daily finance briefing in Markdown about: '{state["topic"]}'.
    You must ONLY use the following recent news to write the report. Do not use prior knowledge.
    
    Raw News Data:
    {state["raw_research"]}
    
    Return ONLY the Markdown report text.
    """
    draft = ask_llm(prompt)
    return {"draft_report": draft.strip()}

def editor_node(state: AgentState):
    print("\n🧐 EDITOR: Reviewing the draft...")
    prompt = f"""
    You are a strict Editor. Review this draft report about '{state["topic"]}'.
    It must be detailed, professional, and properly formatted in Markdown.
    
    Draft Report:
    {state["draft_report"]}
    
    If the report is excellent, reply with EXACTLY the word: APPROVED
    If the report is lacking or too short, reply with the word: REJECTED followed by one sentence of feedback on what to search for next.
    """
    review = ask_llm(prompt).strip()
    
    if review.startswith("APPROVED"):
        print("   -> Editor Decision: APPROVED!")
        return {"status": "approved", "feedback": "", "revision_count": state["revision_count"] + 1}
    else:
        feedback = review.replace("REJECTED", "").strip()
        print(f"   -> Editor Decision: REJECTED. Feedback: {feedback}")
        return {"status": "rejected", "feedback": feedback, "revision_count": state["revision_count"] + 1}

def save_node(state: AgentState):
    print("\n💾 SAVING: Writing to DB and File System...")
    collection.insert_one({"topic": state["topic"], "summary": state["draft_report"]})
    
    os.makedirs("/app/output", exist_ok=True)
    filename = f"/app/output/{state['topic'].replace(' ', '_').lower()}_langgraph_report.md"
    with open(filename, "w") as f:
        f.write(state["draft_report"])
        
    return state

# --- 5. Define the Routing Logic ---
def should_continue(state: AgentState):
    if state["status"] == "approved" or state["revision_count"] >= 3:
        return "save"
    return "researcher"

# --- 6. Build the Graph ---
print("Building the Swarm Graph...")
workflow = StateGraph(AgentState)

workflow.add_node("researcher", searcher_node)
workflow.add_node("analyst", analyst_node)
workflow.add_node("editor", editor_node)
workflow.add_node("save", save_node)

workflow.set_entry_point("researcher")
workflow.add_edge("researcher", "analyst")
workflow.add_edge("analyst", "editor")

workflow.add_conditional_edges(
    "editor",
    should_continue,
    {
        "save": "save",
        "researcher": "researcher"
    }
)
workflow.add_edge("save", END)

app = workflow.compile()

# ==========================================
# --- EXECUTION PIPELINE ---
# ==========================================
if __name__ == "__main__":
    topic = "Finance and job market updates"
    print(f"\n🚀 Starting LangGraph Swarm for: {topic}")
    
    initial_state = {
        "topic": topic,
        "raw_research": "",
        "draft_report": "",
        "feedback": "",
        "status": "",
        "revision_count": 0
    }
    
    app.invoke(initial_state)
    print("\n✅ Pipeline complete. Check the output folder!")