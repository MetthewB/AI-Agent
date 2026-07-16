import os
import time
import logging
import requests
from datetime import datetime, timedelta
import pytz
from typing import TypedDict
from ddgs import DDGS
from icalevents.icalevents import events
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, '.env')
load_dotenv(env_path)

def ask_llm(prompt: str) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY')}",
        "Content-Type": "application/json"
    }
    
    FREE_MODELS = [
        "google/gemma-4-31b-it:free",
        "openai/gpt-oss-20b:free",
        "meta-llama/llama-3.3-70b:free",
        "mistralai/mistral-small:free",
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
            res = requests.post(url, headers=headers, json=payload, timeout=20.0)
            if res.status_code == 200:
                raw_text = res.json().get('choices', [{}])[0].get('message', {}).get('content', '')
                if raw_text and raw_text.strip():
                    return raw_text.strip()
            else:
                print(f"⚠️ {model} failed (Status {res.status_code}). Trying next...")
        except Exception as e:
            print(f"⚠️ {model} connection error: {e}. Trying next...")
            
    return None

def get_weather(lat=46.5197, lon=6.6323):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=auto"
        daily = requests.get(url).json()['daily']
        code = daily['weathercode'][0]
        wmo_map = {0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Foggy", 51: "Light drizzle", 61: "Light rain", 71: "Light snow", 95: "Thunderstorm"}
        return f"{wmo_map.get(code, 'Mixed weather').lower()}, with temperatures going from {daily['temperature_2m_min'][0]} up to {daily['temperature_2m_max'][0]} degrees"
    except: 
        return "Weather unavailable"

def get_calendar_events():
    cal_url = os.environ.get("APPLE_CALENDAR_URL")
    if not cal_url: return "No calendar connected."
    cal_url = cal_url.replace("webcal://", "https://")
    try:
        swiss_tz = pytz.timezone('Europe/Zurich')
        start = datetime.now(swiss_tz).replace(hour=0, minute=0, second=0, microsecond=0)
        cal_events = events(url=cal_url, start=start, end=start + timedelta(days=1))
        if not cal_events: return "Your calendar is clear today."
        cal_events.sort(key=lambda e: e.start)
        agenda_items = []
        for e in cal_events:
            time_str = e.start.astimezone(swiss_tz).strftime('%H:%M')
            display_time = "All day" if time_str == "02:00" else time_str
            agenda_items.append(f"{display_time}: {e.summary}") 
        return "Agenda: " + " | ".join(agenda_items)     
    except Exception as e: 
        print(f"Calendar Error: {e}")
        return "Could not load calendar."

def get_top_news():
    news_items = []
    for emoji, query in [("🌍", "world geopolitics"), ("🇨🇭", "Switzerland breaking news"), ("🇫🇷", "France breaking news")]:
        try:
            for r in DDGS().news(query, max_results=1):
                title = r.get('title', '')
                body = r.get('body', '')
                news_items.append(f"{emoji} {title} - {body}")
        except: pass
    return "\n".join(news_items) if news_items else "No news"

class MorningBriefingState(TypedDict):
    weather: str
    agenda: str
    news: str
    draft: str
    feedback: str
    status: str
    revision_count: int

def briefing_writer_node(state: MorningBriefingState):
    print("\n✍️ WRITER: Drafting morning briefing...")
    if state["revision_count"] > 0:
        time.sleep(2)
    
    today_str = datetime.now().strftime('%A, %B %d, %Y')
    feedback_block = f"PREVIOUS DRAFT WAS REJECTED. FIX THESE ISSUES:\n{state['feedback']}\n\n" if state['feedback'] else ""

    fixed_header = (
        f"Good morning! It is {today_str}. The weather today is {state['weather']}. ☀️\n"
        f"{state['agenda']} 📅"
    )

    prompt = (
        f"You are a morning briefing writer. Output the briefing text only — no preamble, no sign-off, no commentary.\n\n"
        f"{feedback_block}"
        f"The first two lines are already written. Copy them EXACTLY as-is, then add the news blocks below them.\n\n"
        f"FIXED HEADER (copy verbatim, do not alter a single word):\n"
        f"{fixed_header}\n\n"
        f"Now append these 3 news blocks after a blank line:\n\n"
        f"🌍 World: [1-2 sentence summary of world news]\n\n"
        f"🇨🇭 Switzerland: [1-2 sentence summary of Swiss news]\n\n"
        f"🇫🇷 France: [1-2 sentence summary of French news]\n\n"
        f"STRICT RULES:\n"
        f"- Start your output with the fixed header above, copied exactly.\n"
        f"- Follow it with the 3 news blocks, each separated by a blank line.\n"
        f"- No markdown. No asterisks. No bold. No bullet points.\n"
        f"- Total length: under 150 words.\n"
        f"- Each news block must use real details from the news data below.\n\n"
        f"NEWS DATA:\n{state['news']}"
    )
        
    result = ask_llm(prompt)
    if not result:
        logger.error("❌ All models failed, skipping this run.")
        return {"draft": "", "status": "failed"}
    return {"draft": result.strip()}

def validate_draft(draft: str) -> tuple[bool, str]:
    if len(draft.split()) > 180:
        return False, "Too long, keep under 150 words."
    if "Good morning!" not in draft:
        return False, "Missing the fixed header. Start with 'Good morning!'."
    for emoji in ["🌍", "🇨🇭", "🇫🇷"]:
        if emoji not in draft:
            return False, f"Missing {emoji} news block."
    if "**" in draft or "##" in draft or "__" in draft:
        return False, "Contains markdown formatting."
    blocks = [b.strip() for b in draft.split("\n\n") if b.strip()]
    if len(blocks) < 4:
        return False, "Missing double newlines between sections."
    return True, ""

def briefing_editor_node(state: MorningBriefingState):
    print("\n🧐 EDITOR: Validating briefing...")
    if state.get("status") == "failed":
        return state
    approved, feedback = validate_draft(state["draft"])
    if approved:
        return {"status": "approved", "feedback": "", "revision_count": state["revision_count"] + 1}
    return {"status": "rejected", "feedback": feedback, "revision_count": state["revision_count"] + 1}

def send_briefing_node(state: MorningBriefingState):
    print("\n💾 SAVING: Sending Telegram Message...")
    if not state["draft"]:
        print("⚠️ Empty draft, skipping send.")
        return state
    token, chat_id = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try: requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": state["draft"]})
        except Exception as e: print(f"❌ Failed: {e}")
    return state

def routing_logic(state: MorningBriefingState):
    if state.get("status") == "failed" or state["revision_count"] >= 3:
        return "send"
    return "send" if state["status"] == "approved" else "write"

def run_morning_pipeline():
    print("🌅 Gathering Morning Data...")
    workflow = StateGraph(MorningBriefingState)
    workflow.add_node("write", briefing_writer_node)
    workflow.add_node("edit", briefing_editor_node)
    workflow.add_node("send", send_briefing_node)
    workflow.set_entry_point("write")
    workflow.add_edge("write", "edit")
    workflow.add_conditional_edges("edit", routing_logic, {"send": "send", "write": "write"})
    workflow.add_edge("send", END)
    
    print("\n🚀 Starting Morning Swarm...")
    workflow.compile().invoke({"weather": get_weather(), "agenda": get_calendar_events(), "news": get_top_news(), "draft": "", "feedback": "", "status": "", "revision_count": 0})

if __name__ == "__main__":
    run_morning_pipeline()