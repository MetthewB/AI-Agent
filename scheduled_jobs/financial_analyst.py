import os
import time
import requests
from typing import TypedDict
import yfinance as yf
from langgraph.graph import StateGraph, END
from ddgs import DDGS
from dotenv import load_dotenv

load_dotenv()

def ask_llm(prompt: str) -> str:
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
            "max_tokens": 800,
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
        except Exception as e:
            print(f"⚠️ Connection error with {model}: {e}. Skipping to next...")
            
    print("❌ ALL free models on OpenRouter are currently offline or congested.")
    return None

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
        portfolio_data = "\n".join(stats) if stats else "Portfolio data unavailable."
        print(f"   -> Portfolio data fetched:\n{portfolio_data}") 

    return {"raw_research": new_research, "portfolio_data": portfolio_data}

def validate_report(draft: str) -> tuple[bool, str]:
    if len(draft.split()) > 200:
        return False, "Too long, keep under 150 words."
    for section in ["Global Markets", "Portfolio", "Switzerland"]:
        if section not in draft:
            return False, f"Missing '{section}' section."
    if "*" in draft or "##" in draft or "__" in draft:
        return False, "Contains markdown formatting. Remove ALL asterisks and symbols."
    blocks = [b.strip() for b in draft.split("\n\n") if b.strip()]
    if len(blocks) < 3:
        return False, "Missing double newlines between sections."
    return True, ""

def financial_writer_node(state: FinancialReportState):
    print("\n✍️ WRITER: Drafting the financial report...")
    if state["revision_count"] > 0:
        time.sleep(2)

    feedback_block = f"PREVIOUS DRAFT WAS REJECTED. FIX THESE ISSUES:\n{state['feedback']}\n\n" if state['feedback'] else ""

    prompt = (
        f"You are a financial briefing writer. Output the briefing text only — no preamble, no sign-off, no commentary.\n\n"
        f"{feedback_block}"
        f"Write the briefing using EXACTLY this structure (replace bracketed parts):\n\n"
        f"Global Markets: [1-2 sentences on the single most important macro or tech market trend today. Use an emoji.]\n\n"
        f"Portfolio:\n{state['portfolio_data']}\n\n"
        f"Jobs in Switzerland: [2-3 sentences naming specific companies actively hiring for AI, ML, or software roles in Switzerland, including their city locations.]\n\n"
        f"STRICT RULES:\n"
        f"- Output ONLY the briefing. Start with 'Global Markets:' and end after the Switzerland jobs block.\n"
        f"- Separate each of the 3 sections with a blank line.\n"
        f"- No markdown whatsoever. No asterisks, no bold, no italics, no bullet points, no headers. Not even a single * character.\n"
        f"- Do NOT wrap the output in asterisks or any other punctuation.\n"
        f"- Total length: under 150 words.\n"
        f"- The Portfolio block must be reproduced exactly as provided above — do not reword or reformat it.\n"
        f"- The Switzerland jobs section must name real companies and real Swiss cities.\n\n"
        f"NEWS DATA:\n{state['raw_research']}"
    )

    result = ask_llm(prompt)
    if not result:
        print("❌ All models failed, skipping this run.")
        return {"draft_report": "", "status": "failed"}
    
    clean_result = result.strip().strip("*").strip()
    return {"draft_report": clean_result}

def chief_editor_node(state: FinancialReportState):
    print("\n🧐 EDITOR: Validating financial draft...")
    if state.get("status") == "failed":
        return state
    approved, feedback = validate_report(state["draft_report"])
    if approved:
        return {"status": "approved", "feedback": "", "revision_count": state["revision_count"] + 1}
    return {"status": "rejected", "feedback": feedback, "revision_count": state["revision_count"] + 1}

def publish_report_node(state: FinancialReportState):
    print("\n💾 SAVING: Dispatching Telegram Message...")
    if not state["draft_report"]:
        print("⚠️ Empty report, skipping send.")
        return state
    token, chat_id = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": state["draft_report"][:4090]})
            print("   -> 📱 Report sent successfully!")
        except Exception as e:
            print(f"   -> ❌ Failed to send: {e}")
    return state

def routing_logic(state: FinancialReportState):
    if state.get("status") == "failed" or state["revision_count"] >= 3:
        return "publish"
    return "publish" if state["status"] == "approved" else "research"

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
    workflow.compile().invoke({
        "topic": topic,
        "raw_research": "",
        "portfolio_data": "",
        "draft_report": "",
        "feedback": "",
        "status": "",
        "revision_count": 0
    })

if __name__ == "__main__":
    run_financial_pipeline()