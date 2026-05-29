import os
import requests
from datetime import datetime, timedelta
import pytz
from typing import TypedDict
from ddgs import DDGS
from icalevents.icalevents import events
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

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
            "max_tokens": 450,
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
            
    return "APPROVED" if "Review this" in prompt else "Error generating report."

def get_weather(lat=46.5197, lon=6.6323):
    try:
        res = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true").json()
        code = res['current_weather']['weathercode']
        wmo_map = {0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Foggy", 51: "Light drizzle", 61: "Light rain", 71: "Light snow", 95: "Thunderstorm"}
        return f"{res['current_weather']['temperature']}°C and {wmo_map.get(code, 'Mixed weather')}"
    except: return "Weather unavailable"

def get_calendar_events():
    cal_url = os.environ.get("APPLE_CALENDAR_URL")
    if not cal_url: return "No calendar connected."
    cal_url = cal_url.replace("webcal://", "https://")
    try:
        swiss_tz = pytz.timezone('Europe/Zurich')
        start = datetime.now(swiss_tz).replace(hour=0, minute=0, second=0, microsecond=0)
        cal_events = events(url=cal_url, start=start, end=start + timedelta(days=1))
        if not cal_events: return "Your calendar is clear for today."
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
    queries = ["Top world geopolitics today", "Top breaking news Switzerland", "Top breaking news France"]
    news = []
    for q in queries:
        try:
            for r in DDGS().news(q, timelimit="d", max_results=1):
                news.append(r.get('title'))
        except: pass
    return " | ".join(news) if news else "No news updates."

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
    prompt = f"Write a SHORT morning briefing for {datetime.now().strftime('%A, %B %d, %Y')}. Weather: {state['weather']}. {state['agenda']}. News: {state['news']}."
    if state['feedback']: prompt += f"\nFIX THIS: {state['feedback']}"
    prompt += (
        "\nRULES: Be concise. Keep the whole message under 80 words."
        " One short line for weather, one short line for the agenda, and at most 2 brief news headlines (no details)."
        " Normal conversational tone. Exact 3-4 emojis. ABSOLUTELY NO MARKDOWN (no asterisks)."
    )
    return {"draft": ask_llm(prompt).strip()}

def briefing_editor_node(state: MorningBriefingState):
    print("\n🧐 EDITOR: Reviewing briefing...")
    prompt = f"Review this. MUST be concise (under 80 words, one short line each for weather and agenda, max 2 brief news headlines). MUST NOT contain markdown/asterisks. MUST have 3-4 emojis. MUST include weather, agenda, news.\nDraft: {state['draft']}\nIf perfect, reply APPROVED. Else, reply REJECTED followed by instructions."
    review = ask_llm(prompt).strip()
    if review.startswith("APPROVED"): return {"status": "approved", "feedback": "", "revision_count": state["revision_count"] + 1}
    return {"status": "rejected", "feedback": review.replace("REJECTED", "").strip(), "revision_count": state["revision_count"] + 1}

def send_briefing_node(state: MorningBriefingState):
    print("\n💾 SAVING: Sending Telegram Message...")
    token, chat_id = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try: requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": state["draft"]})
        except Exception as e: print(f"❌ Failed: {e}")
    return state

def routing_logic(state: MorningBriefingState):
    return "send" if state["status"] == "approved" or state["revision_count"] >= 3 else "write"

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