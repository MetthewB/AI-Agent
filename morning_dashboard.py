import os
import requests
from datetime import datetime
from huggingface_hub import InferenceClient
from ddgs import DDGS

# --- Setup ---
llm_client = InferenceClient(model="Qwen/Qwen2.5-Coder-32B-Instruct", token=os.environ.get("HF_TOKEN"))

def get_weather(lat=46.5197, lon=6.6323):
    """
    Uses Open-Meteo for Lausanne: 46.5197, 6.6323
    """
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    try:
        res = requests.get(url).json()
        current = res['current_weather']
        temp = current['temperature']
        code = current['weathercode']
        
        # Open-Meteo WMO Weather codes mapping
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

def get_top_news():
    """
    Scrapes the top 2 breaking news stories for the World, Switzerland, and France.
    """
    queries = ["Top general world news today", "Top breaking news Switzerland", "Top breaking news France"]
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

def send_telegram(text):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

def generate_dashboard():
    print("🌅 Building Morning Dashboard...")
    weather_info = get_weather() 
    news_data = get_top_news()
    today = datetime.now().strftime("%A, %B %d, %Y")
    
    prompt = f"""
    You are a helpful personal assistant. Write a morning briefing for {today}.
    
    The current weather in Lausanne is: {weather_info}.
    
    Here is the latest major news from the World, Switzerland, and France:
    {news_data}
    
    RULES:
    - Speak normally and conversationally. Just act like a normal human assistant.
    - Start with a hello and the Lausanne weather.
    - Give a brief, easy-to-read summary of the news (first world news, then swiss news, lastly french news).
    - The news should concern geopolitics and major events.
    - Use emojis naturally to make it visually pleasant, but only 3-4 emojis for the entire message.
    - ABSOLUTELY NO MARKDOWN. Do not use a single asterisk (*), underscore (_), header (#), or bullet point (-). Just pure plain text with emojis.
    """
    
    try:
        messages = [{"role": "user", "content": prompt}]
        response = llm_client.chat_completion(messages=messages, max_tokens=300, temperature=0.3)
        dashboard_text = response.choices[0].message.content.strip()
        send_telegram(dashboard_text)
        print("✅ Morning Dashboard sent successfully!")
    except Exception as e:
        print(f"❌ LLM Error: {e}")

if __name__ == "__main__":
    generate_dashboard()