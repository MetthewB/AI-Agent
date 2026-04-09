import os
import requests
from datetime import datetime, timedelta
import pytz
from typing import TypedDict
from huggingface_hub import InferenceClient
from ddgs import DDGS
from icalevents.icalevents import events
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

load_dotenv()

llm_client = InferenceClient(model="Qwen/Qwen2.5-Coder-32B-Instruct", token=os.environ.get("HF_TOKEN"))

def ask_llm(prompt: str) -> str:
    messages = [{"role": "user", "content": prompt}]
    return llm_client.chat_completion(messages=messages, max_tokens=350, temperature=0.3).choices[0].message.content

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
        return "Agenda: " + " | ".join([f"{e.start.astimezone(swiss_tz).strftime('%H:%M')}: {e.summary}" for e in cal_events])
    except: return "Could not load calendar."

def get_top_news():
    queries = ["Top world geopolitics today", "Top breaking news Switzerland", "Top breaking news France"]
    news = []
    for q in queries:
        try:
            for r in DDGS().news(q, timelimit="d", max_results=2):
                news.append(f"{r.get('title')}: {r.get('body')}")
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
    prompt = f"Write a morning briefing for {datetime.now().strftime('%A, %B %d, %Y')}. Weather: {state['weather']}. {state['agenda']}. News: {state['news']}."
    if state['feedback']: prompt += f"\nFIX THIS: {state['feedback']}"
    prompt += "\nRULES: Normal conversational tone. Exact 3-4 emojis. ABSOLUTELY NO MARKDOWN (no asterisks)."
    return {"draft": ask_llm(prompt).strip()}

def briefing_editor_node(state: MorningBriefingState):
    print("\n🧐 EDITOR: Reviewing briefing...")
    prompt = f"Review this. MUST NOT contain markdown/asterisks. MUST have 3-4 emojis. MUST include weather, agenda, news.\nDraft: {state['draft']}\nIf perfect, reply APPROVED. Else, reply REJECTED followed by instructions."
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