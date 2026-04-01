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
        return f"{temp}°C"
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
            # We fetch just the top 2 news items per region to keep the context clean
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
    weather_temp = get_weather() 
    news_data = get_top_news()
    today = datetime.now().strftime("%A, %B %d, %Y")
    
    prompt = f"""
    You are a luxury digital concierge. Write a 'Good Morning' briefing for {today}.
    
    The current temperature in Lausanne is {weather_temp}.
    
    Here is the latest major news from the World, Switzerland, and France:
    {news_data}
    
    RULES:
    - Write a seamless, elegant 2 to 3 paragraph morning greeting.
    - Start with a warm greeting and the Lausanne weather.
    - Summarize the most important news stories gracefully. 
    - EXCLUDE any boring financial or stock market news. Focus on general major events.
    - Use elegant emojis naturally (🇨🇭, 🇫🇷, 🌍, ☕).
    - Use a sophisticated, helpful tone.
    - ABSOLUTELY NO Markdown formatting (no asterisks **, no headers ###, no bullet points -). Pure plain text.
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