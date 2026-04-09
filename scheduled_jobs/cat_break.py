import os
import requests
from dotenv import load_dotenv

load_dotenv()

def dispatch_daily_cat():
    print("🐾 Fetching morning cat break...")
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    cat_api_url = "https://api.thecatapi.com/v1/images/search?mime_types=gif"
    
    try:
        response = requests.get(cat_api_url).json()
        gif_url = response[0]['url']
        
        telegram_url = f"https://api.telegram.org/bot{token}/sendAnimation"
        payload = {"chat_id": chat_id, "animation": gif_url}
        
        res = requests.post(telegram_url, json=payload)
        if res.status_code == 200:
            print("✅ Cat GIF dispatched successfully!")
        else:
            print(f"❌ Telegram API Error: {res.text}")
            
    except Exception as e:
        print(f"❌ Failed to fetch or send cat GIF: {e}")

if __name__ == "__main__":
    dispatch_daily_cat()