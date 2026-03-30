import os
from datetime import datetime
from typing import TypedDict
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from langgraph.graph import StateGraph, END
from huggingface_hub import InferenceClient
from ddgs import DDGS

# --- 1. AI Model Setup ---
llm_client = InferenceClient(
    model="Qwen/Qwen2.5-Coder-32B-Instruct",
    token=os.environ.get("HF_TOKEN")
)

def ask_llm(prompt: str) -> str:
    messages = [{"role": "user", "content": prompt}]
    response = llm_client.chat_completion(
        messages=messages, 
        max_tokens=1024, 
        temperature=0.3
    )
    return response.choices[0].message.content

# --- 2. Define the State ---
class AgentState(TypedDict):
    topic: str
    raw_research: str
    draft_report: str
    feedback: str
    status: str  
    revision_count: int

# --- 3. Define the Nodes ---
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
    Write a highly concise, 2 to 3 paragraph daily briefing about: '{state["topic"]}'.
    
    CRITICAL FORMATTING RULES:
    - DO NOT use ANY Markdown formatting.
    - NO bolding with asterisks (like **this**).
    - NO headers (like ###) or horizontal rules (like ---).
    - NO bullet points. 
    - USE EMOJIS naturally within the text to separate ideas and make it visually appealing for a mobile chat (e.g., 🌍 for Global Markets, 📈 for Stocks, 🇨🇭 for Swiss Jobs).
    
    Your short briefing MUST seamlessly combine and cover:
    1. Global Market Trends
    2. Specific Stocks (Buy/Sell/Watch Signals)
    3. The Swiss Engineering Job Market

    Keep it extremely brief and punchy. You must ONLY use the following recent news to write the report. Do not hallucinate data.
    
    Raw News Data:
    {state["raw_research"]}
    
    Return ONLY the final message text.
    """
    draft = ask_llm(prompt)
    return {"draft_report": draft.strip()}

def editor_node(state: AgentState):
    print("\n🧐 EDITOR: Reviewing the draft...")
    prompt = f"""
    You are a strict Editor. Review this draft report.
    
    CRITICAL REQUIREMENTS:
    1. It MUST be short (only 2 or 3 paragraphs).
    2. It MUST NOT contain any Markdown formatting whatsoever (no headers like ###, no bullet points -, and absolutely no bolding with **). It should be pure plain text with emojis.
    3. It MUST explicitly mention specific stocks with buy/watch/sell context.
    4. It MUST explicitly discuss the engineering job market in Switzerland.
    
    Draft Report:
    {state["draft_report"]}
    
    If the report meets ALL requirements, reply with EXACTLY the word: APPROVED
    If the report uses any asterisks (**), Markdown headers, is too long, or misses specific stock/Swiss data, reply with the word: REJECTED followed by feedback on what to fix or a specific search query the Searcher should use next.
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
    print("\n💾 SAVING: Dispatching Notifications...")
    
    # Telegram Delivery
    telegram_token = os.environ.get("TELEGRAM_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if telegram_token and telegram_chat_id:
        try:
            print("   -> Attempting to send Telegram message...")
            url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
            text_to_send = state["draft_report"][:4090] 
            
            payload = {"chat_id": telegram_chat_id, "text": text_to_send}
            
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                print("   -> 📱 Telegram message sent successfully!")
            else:
                print(f"   -> ❌ Telegram API Error: {response.text}")
        except Exception as e:
            print(f"   -> ❌ Failed to send Telegram message: {e}")
        
    return state

def should_continue(state: AgentState):
    if state["status"] == "approved" or state["revision_count"] >= 3:
        return "save"
    return "researcher"

# --- 4. Build and Run ---
workflow = StateGraph(AgentState)
workflow.add_node("researcher", searcher_node)
workflow.add_node("analyst", analyst_node)
workflow.add_node("editor", editor_node)
workflow.add_node("save", save_node)

workflow.set_entry_point("researcher")
workflow.add_edge("researcher", "analyst")
workflow.add_edge("analyst", "editor")
workflow.add_conditional_edges("editor", should_continue, {"save": "save", "researcher": "researcher"})
workflow.add_edge("save", END)

app = workflow.compile()

if __name__ == "__main__":
    topic = "Global stock market trends, specific stocks to buy/sell, and the engineering job market in Switzerland"
    print(f"\n🚀 Starting GitHub Actions Swarm for: {topic}")
    app.invoke({"topic": topic, "raw_research": "", "draft_report": "", "feedback": "", "status": "", "revision_count": 0})
    print("\n✅ Serverless Pipeline complete.")