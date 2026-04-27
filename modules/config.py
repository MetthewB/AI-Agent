import os
import logging
import certifi
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# ==========================================
# ENVIRONMENT VARIABLES
# ==========================================
TOKEN = os.environ.get("TELEGRAM_TOKEN")
HF_TOKEN = os.environ.get("HF_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
CHAT_ID_ENV = os.environ.get("TELEGRAM_CHAT_ID", "0")
STRAVA_CLIENT_ID = os.environ.get("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.environ.get("STRAVA_CLIENT_SECRET")
STRAVA_REFRESH_TOKEN = os.environ.get("STRAVA_REFRESH_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")

# ==========================================
# VIP AUTHORIZATION LIST
# ==========================================
AUTHORIZED_USERS = []
if CHAT_ID_ENV:
    for uid in CHAT_ID_ENV.split(","):
        clean_uid = uid.strip()
        if clean_uid.replace("-", "").isdigit():
            AUTHORIZED_USERS.append(int(clean_uid))

logger.info(f"✅ VIP List Loaded: {AUTHORIZED_USERS}")

# ==========================================
# STATIC DATA MAPS
# ==========================================
PORTFOLIO_MAP = {
    "EUNL.DE": "MSCI World (EUNL)",
    "EUNM.DE": "MSCI Emerging Mkts (EUNM)",
    "ACM9.DE": "MSCI World SRI (ACM9)",
    "GLD": "Gold (XAU)"
}

WMO_WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Foggy", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Light snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Light showers", 81: "Moderate showers", 82: "Heavy showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Heavy thunderstorm"
}

# ==========================================
# DATABASE SETUP (MONGODB)
# ==========================================
grocery_collection = None

if MONGO_URI:
    from database import db 
    grocery_collection = db.groceries
else:
    logger.warning("⚠️ MONGO_URI is missing! Groceries won't be saved.")