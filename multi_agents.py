import os
from datetime import datetime
from typing import TypedDict
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
    print("\n🔍 SEARCHER: Gathering information...")
    query = state["topic"]
    if state["feedback"]:
        print(f"   -> Adjusting search based on feedback: {state['feedback']}")
        query = state['feedback']

    try:
        results = DDGS().news(query, timelimit="d", max_results=5)
        
        if not results:
            print("   -> No daily news found. Expanding search to the past month...")
            results = DDGS().text(query, timelimit="m", max_results=5)
            
        snippets = "\n".join([f"- [{r.get('date', 'Recent')}] {r.get('title', '')}: {r.get('body', '')}" for r in results])
    except Exception as e:
        print(f"   -> Search API Error: {e}")
        print("   -> Attempting unfiltered emergency web search...")
        try:
            results = DDGS().text(query, max_results=3)
            snippets = "\n".join([f"- {r.get('title', '')}: {r.get('body', '')}" for r in results])
        except:
            snippets = "The search engine blocked the request. Please provide general macro analysis."
        
    new_research = state["raw_research"] + "\n" + snippets
    return {"raw_research": new_research}

def analyst_node(state: AgentState):
    print("\n✍️ ANALYST: Writing the report...")
    today = datetime.now().strftime("%A, %B %d, %Y")
    
    prompt = f"""
    You are an expert Financial and Career Analyst. Today is {today}. 
    Write a highly structured daily briefing in Markdown about: '{state["topic"]}'.
    
    Structure your report with the following EXACT headers:
    ### 1. Global Market Trends
    (Summarize the broader economic news of the day)
    
    ### 2. Stock Watchlist (Buy/Sell Signals)
    (Name specific stocks and whether the recent news implies a bullish or bearish outlook. Note: State that this is for informational purposes, not financial advice.)
    
    ### 3. Swiss Engineering Job Market
    (Highlight specific news, hiring trends, or updates regarding the engineering sector in Switzerland)

    You must ONLY use the following recent news to write the report. Do not hallucinate data.
    
    Raw News Data:
    {state["raw_research"]}
    
    Return ONLY the Markdown report text.
    """
    draft = ask_llm(prompt)
    return {"draft_report": draft.strip()}

def editor_node(state: AgentState):
    print("\n🧐 EDITOR: Reviewing the draft...")
    prompt = f"""
    You are a strict Editor. Review this draft report.
    
    CRITICAL REQUIREMENTS:
    1. It MUST explicitly mention specific stocks with buy/watch/sell context.
    2. It MUST explicitly discuss the engineering job market in Switzerland.
    
    Draft Report:
    {state["draft_report"]}
    
    If the report meets ALL requirements and uses data, reply with EXACTLY the word: APPROVED
    If the report is missing specific stock tickers, or missing Swiss engineering news, reply with the word: REJECTED followed by a specific search query the Searcher should use next (e.g., "REJECTED Search for recent hiring trends for engineers in Switzerland").
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
    print("\n💾 SAVING: Writing to DB, File System, and Dispatching Email...")
    
    collection.insert_one({"topic": state["topic"], "summary": state["draft_report"]})
    
    os.makedirs("/app/output", exist_ok=True)
    filename = f"/app/output/daily_swiss_finance_briefing.md"
    with open(filename, "w") as f:
        f.write(state["draft_report"])
        
    sender_email = os.environ.get("SENDER_EMAIL")
    sender_password = os.environ.get("SENDER_PASSWORD")
    receiver_email = os.environ.get("RECEIVER_EMAIL")

    if sender_email and sender_password and receiver_email:
        try:
            print("   -> Attempting to send email...")
            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = receiver_email
            msg['Subject'] = f"Swiss Engineering & Global Markets Daily Briefing"
            
            msg.attach(MIMEText(state["draft_report"], 'plain'))
            
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
            server.quit()
            print("   -> 📧 Email sent successfully!")
        except Exception as e:
            print(f"   -> ❌ Failed to send email: {e}")
    else:
        print("   -> ⚠️ Email credentials not found. Skipping email delivery.")
        
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
    topic = "Global stock market trends, specific stocks to buy/sell, and the engineering job market in Switzerland"
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