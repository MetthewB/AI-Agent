import os
import requests
from datetime import datetime, timedelta
import pytz
from typing import TypedDict
from huggingface_hub import InferenceClient
from ddgs import DDGS
from icalevents.icalevents import events
from langgraph.graph import StateGraph, END

# --- Setup ---
llm_client = InferenceClient(model="Qwen/Qwen2.5-Coder-32B-Instruct", token=os.environ.get("HF_TOKEN"))

def ask_llm(prompt: str) -> str:
    messages = [{"role": "user", "content": prompt}]
    response = llm_client.chat_completion(messages=messages, max_tokens=350, temperature=0.3)
    return response.choices[0].message.content

# --- 1. Data Gathering Functions ---
def get_weather(lat=46.5197, lon=6.6323):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    try:
        res = requests.get(url).json()
        current = res['current_weather']
        temp = current['temperature']
        code = current['weathercode']
        wmo_map = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Foggy", 48: "Foggy", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
            61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
            71: "Light snow", 73: "Moderate snow", 75: "Heavy snow",
            80: "Light showers", 81: "Moderate showers", 82: "Heavy showers",
            95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Heavy thunderstorm"
        }
        condition = wmo_map.get(code, "Mixed weather")
        return f"{temp}°C and {condition}"
    except Exception as e:
        print(f"Weather Error: {e}")
        return "Weather data temporarily unavailable"

def get_calendar_events():
    cal_url = os.environ.get("APPLE_CALENDAR_URL")
    if not cal_url:
        return "No calendar connected."
    if cal_url.startswith("webcal://"):
        cal_url = cal_url.replace("webcal://", "https://")
    try:
        swiss_tz = pytz.timezone('Europe/Zurich')
        today_start = datetime.now(swiss_tz).replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        cal_events = events(url=cal_url, start=today_start, end=today_end)
        if not cal_events:
            return "Your calendar is clear for today."
        cal_events.sort(key=lambda e: e.start)
        agenda = []
        for e in cal_events:
            time_str = e.start.astimezone(swiss_tz).strftime('%H:%M')
            agenda.append(f"{time_str}: {e.summary}")
        return "Today's Agenda: " + " | ".join(agenda)
    except Exception as e:
        print(f"Calendar Error: {e}")
        return "Could not load calendar events for today."

def get_top_news():
    queries = ["Top general world news geopolitics today", "Top breaking news geopolitics Switzerland", "Top breaking news geopolitics France"]
    news_snippets = []
    for q in queries:
        try:
            results = DDGS().news(q, timelimit="d", max_results=2)
            for r in results:
                news_snippets.append(f"{r.get('title')}: {r.get('body')}")
        except Exception as e:
            print(f"Search API Error for '{q}': {e}")
    if not news_snippets:
        return "No major news updates available right now."
    return " | ".join(news_snippets)

# --- 2. Define the Graph State ---
class DashboardState(TypedDict):
    weather: str
    agenda: str
    news: str
    draft: str
    feedback: str
    status: str
    revision_count: int

# --- 3. Define the Nodes ---
def writer_node(state: DashboardState):
    print("\n✍️ WRITER: Drafting the morning dashboard...")
    today = datetime.now().strftime("%A, %B %d, %Y")
    
    prompt = f"""
    You are a helpful personal assistant. Write a morning briefing for {today}.
    
    The current weather in Lausanne is: {state['weather']}
    {state['agenda']}
    Here is the latest major news (World, Switzerland, France):
    {state['news']}
    """
    
    if state['feedback']:
        prompt += f"\n\nCRITICAL EDITOR FEEDBACK TO FIX: {state['feedback']}\n"
        
    prompt += """
    RULES:
    - Speak normally and conversationally. Just act like a normal human assistant.
    - Start with a hello, the Lausanne weather, and mention the user's calendar schedule for today.
    - Give a brief, easy-to-read summary of the news (first world, then swiss, then french). Focus ONLY on geopolitics and major events.
    - Use EXACTLY 3 or 4 emojis for the entire message to make it visually pleasant.
    - ABSOLUTELY NO MARKDOWN. Do not use a single asterisk (*), underscore (_), header (#), or bullet point (-). Just pure plain text.
    """
    
    draft = ask_llm(prompt)
    return {"draft": draft.strip()}

def editor_node(state: DashboardState):
    print("\n🧐 EDITOR: Reviewing the draft...")
    prompt = f"""
    You are a strict Editor. Review this morning briefing draft.
    
    CRITICAL REQUIREMENTS:
    1. It MUST NOT contain any markdown formatting (no asterisks *, no underscores _, no headers #, no bullet points -).
    2. It MUST contain exactly 3 or 4 emojis total. Count them.
    3. It MUST include the weather, the calendar agenda, and the news.
    
    Draft Report:
    {state['draft']}
    
    If the draft meets ALL requirements perfectly, reply with EXACTLY the word: APPROVED
    If the draft uses markdown, has the wrong amount of emojis, or misses schedule/news data, reply with the word: REJECTED followed by exactly what the Writer needs to fix.
    """
    review = ask_llm(prompt).strip()
    
    if review.startswith("APPROVED"):
        print("   -> Editor Decision: APPROVED!")
        return {"status": "approved", "feedback": "", "revision_count": state["revision_count"] + 1}
    else:
        feedback = review.replace("REJECTED", "").strip()
        print(f"   -> Editor Decision: REJECTED. Feedback: {feedback}")
        return {"status": "rejected", "feedback": feedback, "revision_count": state["revision_count"] + 1}

def send_node(state: DashboardState):
    print("\n💾 SAVING: Dispatching Telegram Message...")
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": state["draft"]})
            print("   -> 📱 Telegram message sent successfully!")
        except Exception as e:
            print(f"   -> ❌ Failed to send Telegram message: {e}")
    return state

def should_continue(state: DashboardState):
    # If approved or we tried 3 times, move to send so we don't get stuck in an infinite loop
    if state["status"] == "approved" or state["revision_count"] >= 3:
        return "send"
    return "writer"

# --- 4. Build and Run the Graph ---
def generate_dashboard():
    print("🌅 Gathering Morning Data...")
    weather = get_weather()
    agenda = get_calendar_events()
    news = get_top_news()
    
    workflow = StateGraph(DashboardState)
    workflow.add_node("writer", writer_node)
    workflow.add_node("editor", editor_node)
    workflow.add_node("send", send_node)
    
    workflow.set_entry_point("writer")
    workflow.add_edge("writer", "editor")
    workflow.add_conditional_edges("editor", should_continue, {"send": "send", "writer": "writer"})
    workflow.add_edge("send", END)
    
    app = workflow.compile()
    
    print("\n🚀 Starting Dashboard Swarm...")
    app.invoke({
        "weather": weather, 
        "agenda": agenda, 
        "news": news, 
        "draft": "", 
        "feedback": "", 
        "status": "", 
        "revision_count": 0
    })

if __name__ == "__main__":
    generate_dashboard()