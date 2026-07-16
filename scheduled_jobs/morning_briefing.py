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
            
    return "REJECTED: All models unavailable." if "Review this" in prompt else "Error generating report."

def get_weather(lat=46.5197, lon=6.6323):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=auto"
        daily = requests.get(url).json()['daily']
        code = daily['weathercode'][0]
        wmo_map = {0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Foggy", 51: "Light drizzle", 61: "Light rain", 71: "Light snow", 95: "Thunderstorm"}
        return f"{wmo_map.get(code, 'Mixed weather').lower()}, with temperatures going from {daily['temperature_2m_min'][0]}°C up to {daily['temperature_2m_max'][0]}°C"
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
    today_str = datetime.now().strftime('%A, %B %d, %Y')
    
    prompt = f"""
    Write a morning briefing.
    
    REQUIRED STRUCTURE AND TONE (Conversational & Warm):
    Good morning! It is {today_str}. The weather today is {state['weather']}. [Weather Emoji]
    {state['agenda']} [Coffee/Calendar Emoji]
    
    [News Paragraph 1]
    
    [News Paragraph 2]
    
    [News Paragraph 3]

    NEWS RULES:
    - You must write exactly 3 distinct news blocks separated by double newlines (one for 🌍, one for 🇨🇭, and one for 🇫🇷).
    - Start each news block directly with its emoji (🌍, 🇨🇭, or 🇫🇷) followed by prefixes like "World:", "Switzerland:", or "France:", immediatly followed by the informative 1-2 sentence summary.
    
    CRITICAL FORMATTING RULES:
    - ABSOLUTELY NO MARKDOWN (no asterisks, no headers, no bolding).
    - No filler text, intro preambles, or closing sign-offs.

    News Data Context:
    {state['news']}

    RULES: 
    - Keep the exact greeting format above.
    - Keep it under 150 words.
    - Make sure the news points are informative and give actual details.
    - Do not add any filler text, preamble, or sign-offs.
    - ABSOLUTELY NO MARKDOWN (no asterisks, no bolding).
    """
    
    if state['feedback']: 
        prompt += f"\nFIX THIS FROM PREVIOUS DRAFT: {state['feedback']}"
        
    return {"draft": ask_llm(prompt).strip()}

def briefing_editor_node(state: MorningBriefingState):
    print("\n🧐 EDITOR: Reviewing briefing...")
    prompt = f"""
    Review this briefing draft. 
    
    CRITICAL CHECKLIST:
    1. It MUST have double newlines separating the greeting/agenda from the news, and double newlines separating each of the 3 news blocks.
    2. The 3 news blocks MUST start directly with their emojis (🌍, 🇨🇭, 🇫🇷). 
    3. There MUST be written label prefixes (like "World:", "France:", etc.) right after the emojis.
    4. There MUST be ZERO markdown or asterisks anywhere in the text.
    5. The text must be under 150 words total.
    
    Draft: 
    {state['draft']}
    
    If perfect, reply EXACTLY: APPROVED. Else, reply REJECTED followed by raw instructions on what to fix.
    """    
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