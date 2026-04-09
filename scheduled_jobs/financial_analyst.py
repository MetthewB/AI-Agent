import os
from datetime import datetime
from typing import TypedDict
import requests
import yfinance as yf
from langgraph.graph import StateGraph, END
from huggingface_hub import InferenceClient
from ddgs import DDGS
from dotenv import load_dotenv

load_dotenv()

llm_client = InferenceClient(model="Qwen/Qwen2.5-Coder-32B-Instruct", token=os.environ.get("HF_TOKEN"))

def ask_llm(prompt: str) -> str:
    messages = [{"role": "user", "content": prompt}]
    response = llm_client.chat_completion(messages=messages, max_tokens=1024, temperature=0.3)
    return response.choices[0].message.content

class FinancialReportState(TypedDict):
    topic: str
    raw_research: str
    portfolio_data: str
    draft_report: str
    feedback: str
    status: str  
    revision_count: int

def market_researcher_node(state: FinancialReportState):
    print("\n🔍 RESEARCHER: Gathering market information...")
    query = state.get("feedback") or state["topic"]

    try:
        results = DDGS().news(query, timelimit="d", max_results=5)
        if not results:
            results = DDGS().text(query, timelimit="m", max_results=5)
        snippets = "\n".join([f"- [{r.get('date', 'Recent')}] {r.get('title', '')}: {r.get('body', '')}" for r in results])
    except Exception as e:
        snippets = f"Search Error: {e}"
        
    new_research = state["raw_research"] + "\n" + snippets

    portfolio_data = state.get("portfolio_data", "")
    if not portfolio_data:
        print("   -> Fetching live portfolio data...")
        portfolio_map = {
            "EUNL.DE": "MSCI World (EUNL)", "EUNM.DE": "MSCI Emerging Mkts (EUNM)",
            "ACM9.DE": "MSCI World SRI (ACM9)", "XAUUSD=X": "Gold (XAU)"
        }
        stats = []
        for ticker, name in portfolio_map.items():
            try:
                hist = yf.Ticker(ticker).history(period="2d")
                if len(hist) >= 2:
                    current, prev = hist['Close'].iloc[-1], hist['Close'].iloc[-2]
                    stats.append(f"{name}: {current:.2f} ({((current - prev) / prev) * 100:+.2f}%)")
            except: pass
        portfolio_data = "USER PORTFOLIO DATA: " + " | ".join(stats)

    return {"raw_research": new_research, "portfolio_data": portfolio_data}

def financial_writer_node(state: FinancialReportState):
    print("\n✍️ WRITER: Drafting the financial report...")
    today = datetime.now().strftime("%A, %B %d, %Y")
    
    prompt = f"""
    You are an expert Financial Analyst. Today is {today}. 
    Write a highly concise, 2 to 3 paragraph daily briefing about: '{state["topic"]}'.
    
    CRITICAL RULES:
    - NEVER use asterisks (*). No Markdown formatting.
    - Use emojis naturally to separate ideas.
    - Combine Global Market Trends, USER PORTFOLIO updates (using exact numbers below), and Swiss Engineering Job Market news.
    
    Raw News Data:
    {state["raw_research"]}

    Live Portfolio Data:
    {state["portfolio_data"]}
    """
    return {"draft_report": ask_llm(prompt).strip()}

def chief_editor_node(state: FinancialReportState):
    print("\n🧐 EDITOR: Reviewing financial draft...")
    prompt = f"""
    Review this draft. It MUST be short (2-3 paragraphs), have ZERO markdown/asterisks, and explicitly mention the portfolio (EUNL, EUNM, ACM9, Gold) and Swiss engineering jobs.
    Draft: {state["draft_report"]}
    If perfect, reply EXACTLY: APPROVED. Otherwise, reply REJECTED followed by what to fix.
    """
    review = ask_llm(prompt).strip()
    
    if review.startswith("APPROVED"):
        print("   -> Decision: APPROVED!")
        return {"status": "approved", "feedback": "", "revision_count": state["revision_count"] + 1}
    print(f"   -> Decision: REJECTED. Fixes: {review.replace('REJECTED', '')}")
    return {"status": "rejected", "feedback": review.replace("REJECTED", "").strip(), "revision_count": state["revision_count"] + 1}

def publish_report_node(state: FinancialReportState):
    print("\n💾 SAVING: Dispatching Telegram Message...")
    token, chat_id = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": state["draft_report"][:4090]})
            print("   -> 📱 Report sent successfully!")
        except Exception as e: print(f"   -> ❌ Failed to send: {e}")
    return state

def routing_logic(state: FinancialReportState):
    return "publish" if state["status"] == "approved" or state["revision_count"] >= 3 else "research"

def run_financial_pipeline():
    workflow = StateGraph(FinancialReportState)
    workflow.add_node("research", market_researcher_node)
    workflow.add_node("write", financial_writer_node)
    workflow.add_node("edit", chief_editor_node)
    workflow.add_node("publish", publish_report_node)
    
    workflow.set_entry_point("research")
    workflow.add_edge("research", "write")
    workflow.add_edge("write", "edit")
    workflow.add_conditional_edges("edit", routing_logic, {"publish": "publish", "research": "research"})
    workflow.add_edge("publish", END)
    
    topic = "Global stock market trends, specific stocks to buy/sell, and the engineering job market in Switzerland"
    print(f"\n🚀 Starting Financial Pipeline for: {topic}")
    workflow.compile().invoke({"topic": topic, "raw_research": "", "portfolio_data": "", "draft_report": "", "feedback": "", "status": "", "revision_count": 0})

if __name__ == "__main__":
    run_financial_pipeline()