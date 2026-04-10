import os
import requests
from dotenv import load_dotenv

# Load the secrets from your existing .env file
load_dotenv()

CLIENT_ID = os.environ.get("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.environ.get("STRAVA_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    print("❌ ERROR: Missing Strava credentials in your .env file!")
    exit()

print("🔗 Please go to this URL to authorize your app:")
print(f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=force&scope=activity:read_all")
print("-" * 50)

CODE = input("Paste your authorization CODE here: ").strip()

url = "https://www.strava.com/oauth/token"
payload = {
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "code": CODE,
    "grant_type": "authorization_code"
}

response = requests.post(url, data=payload)
data = response.json()

if "refresh_token" in data:
    print("\n🎉 SUCCESS! Copy this token and put it in your .env file as STRAVA_REFRESH_TOKEN:")
    print("-" * 50)
    print(data.get("refresh_token"))
    print("-" * 50)
else:
    print("\n❌ FAILED. Strava returned this error:")
    print(data)