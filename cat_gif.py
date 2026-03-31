import os
import requests

def send_cat_gif():
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    # Using a free public API to get a random cat GIF
    cat_api_url = "https://api.thecatapi.com/v1/images/search?mime_types=gif"
    
    try:
        # 1. Get the GIF URL
        response = requests.get(cat_api_url).json()
        gif_url = response[0]['url']
        
        # 2. Send to Telegram
        telegram_url = f"https://api.telegram.org/bot{token}/sendAnimation"
        payload = {
            "chat_id": chat_id,
            "animation": gif_url,
        }
        
        res = requests.post(telegram_url, json=payload)
        if res.status_code == 200:
            print("✅ Cat GIF dispatched successfully!")
        else:
            print(f"❌ Telegram API Error: {res.text}")
            
    except Exception as e:
        print(f"❌ Failed to fetch or send cat GIF: {e}")

if __name__ == "__main__":
    send_cat_gif()