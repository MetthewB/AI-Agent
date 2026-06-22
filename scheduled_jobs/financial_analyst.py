import os
import requests
from datetime import datetime
from typing import TypedDict
import yfinance as yf
from langgraph.graph import StateGraph, END
from ddgs import DDGS
from dotenv import load_dotenv

load_dotenv()

def ask_llm(prompt: str) -> str:
    """Routes the financial analysis prompt to OpenRouter using free models with a fallback chain."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY')}",
        "Content-Type": "application/json"
    }
    
    FREE_MODELS = [
        "google/gemma-4-31b-it:free",
        "openai/gpt-oss-20b:free",
        "meta-llama/llama-3-8b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
        "openrouter/auto"
    ]

    for model in FREE_MODELS:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 450,
            "temperature": 0.4
        }
        
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=15.0)
            
            if res.status_code == 200:
                raw_text = res.json().get('choices', [{}])[0].get('message', {}).get('content', '')
                if raw_text.strip():
                    return raw_text.strip()
            else:
                print(f"⚠️ Free model {model} failed with status {res.status_code}. Trying next...")
                continue
                
        except Exception as e:
            print(f"⚠️ Connection error with {model}: {e}. Skipping to next...")
            continue
            
    print("❌ ALL free models on OpenRouter are currently offline or congested.")

    return "APPROVED" if "Review this" in prompt else "Error analyzing financial data."

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
    query = state.get("feedback") or f"{state['topic']} AND (Swiss AI jobs OR Switzerland tech hiring)"
    try:
        results = DDGS().news(query, timelimit="d", max_results=3) or DDGS().text(query, timelimit="m", max_results=3)
        snippets = "\n".join([f"- {r.get('title', '')}: {r.get('body', '')}" for r in results])
    except Exception as e:
        snippets = f"Search Error: {e}"
        
    new_research = state["raw_research"] + "\n" + snippets

    portfolio_data = state.get("portfolio_data", "")
    if not portfolio_data:
        print("   -> Fetching live portfolio data...")
        portfolio_map = {
            "EUNL.DE": "MSCI World (EUNL)", 
            "EUNM.DE": "MSCI Emerging Markets (EUNM)", 
            "DE5A.DE": "Euro Government Bond (DE5A)", 
            "GC=F": "Gold (XAU)"
        }
        stats = []
        for ticker, name in portfolio_map.items():
            try:
                hist = yf.Ticker(ticker).history(period="2d")
                if len(hist) >= 2:
                    curr, prev = hist['Close'].iloc[-1], hist['Close'].iloc[-2]
                    pct = ((curr - prev) / prev) * 100
                    stats.append(f"{name}: {curr:.2f} ({pct:+.2f}%) {'📈' if pct >= 0 else '📉'}")
            except: pass
        portfolio_data = "\n".join(stats)

    return {"raw_research": new_research, "portfolio_data": portfolio_data}

def financial_writer_node(state: FinancialReportState):
    print("\n✍️ WRITER: Drafting the financial report...")
    prompt = f"""
    Write a clean daily financial briefing. Keep it under 150 words total.
    
    CRITICAL STRUCTURE (You MUST separate these 3 blocks with double newlines):
    [Global Markets Paragraph]
    
    [Portfolio Block]
    
    [Swiss Engineering Jobs Paragraph]

    RULES:
    1. Global Markets: Highlight the single most important global macro trend or tech tilt today.
    2. Portfolio Block: Output the exact raw lines provided below as-is.
    3. Swiss Engineering Jobs: Focus explicitly on AI-oriented roles, Machine Learning, and software talent. Mention active companies with job offers and their locations in Switzerland (e.g., IBM in Zurich, Merck in Aubonne, or others found in the news data).
    4. Formatting: ABSOLUTELY NO MARKDOWN (no asterisks, no bolding, no headers). 
    5. Emojis: Use a few emojis naturally to break up the flow.

    Exact Portfolio Block to Output:
    {state["portfolio_data"]}

    News Data for Context:
    {state["raw_research"]}
    """
    return {"draft_report": ask_llm(prompt).strip()}

def chief_editor_node(state: FinancialReportState):
    print("\n🧐 EDITOR: Reviewing financial draft...")
    prompt = f"""
    Review this draft. 
    - It MUST be under 150 words.
    - It MUST have double newlines separating Markets, Portfolio, and Swiss Jobs.
    - It MUST have ZERO markdown/asterisks.
    - The Swiss Jobs section MUST explicitly focus on AI engineering talent and name companies along with their specific Swiss locations.
    
    Draft: 
    {state["draft_report"]}
    
    If perfect, reply APPROVED. Otherwise, reply REJECTED followed by raw instructions.
    """
    review = ask_llm(prompt).strip()
    if review.startswith("APPROVED"):
        return {"status": "approved", "feedback": "", "revision_count": state["revision_count"] + 1}
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