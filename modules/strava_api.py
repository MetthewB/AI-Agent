import re
import asyncio
import logging
import requests

# Import credentials from your config module
from modules.config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN

# Set up logging for this specific module
logger = logging.getLogger(__name__)

# ==========================================
# 1. AUTHENTICATION
# ==========================================
async def get_strava_access_token() -> str:
    """Uses the refresh token to get a temporary access token for Strava."""
    if not all([STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN]):
        logger.error("❌ Missing Strava credentials in environment variables.")
        return None
        
    url = "https://www.strava.com/oauth/token"
    payload = {
        "client_id": STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": STRAVA_REFRESH_TOKEN
    }
    try:
        # We use asyncio.to_thread so the blocking requests.post doesn't freeze the bot
        res = await asyncio.to_thread(requests.post, url, data=payload, timeout=10)
        return res.json().get("access_token")
    except Exception as e:
        logger.error(f"❌ Strava Token Error: {e}")
        return None

# ==========================================
# 2. DATA FETCHING
# ==========================================
async def get_recent_strava_activities(limit: int = 5) -> str:
    """Fetches latest activities and extracts all data including duration and Coros Load."""
    access_token = await get_strava_access_token()
    if not access_token: 
        return "No Strava data available."
    
    url = f"https://www.strava.com/api/v3/athlete/activities?per_page={limit}"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        res = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
        activities = res.json()
        if not activities: 
            return "No recent history."
        
        history = []
        for act in activities:
            name = act.get('name', 'Workout')
            desc = act.get('description', '') or ''
            date_str = act.get('start_date_local', 'Unknown Date')[:10]
            dist = act.get('distance', 0) / 1000
            moving_time_sec = act.get('moving_time', 0)
            duration_min = moving_time_sec // 60
            
            hr = act.get('average_heartrate', 'N/A')
            
            # Extract Coros Load if it exists in the description
            coros_load = "Unknown"
            if "charge d'entraînement" in desc:
                match = re.search(r'(\d+)\s*charge', desc)
                if match:
                    coros_load = match.group(1)

            history.append(
                f"- {date_str} | Title: '{name}' | Dist: {dist:.1f}km | "
                f"Duration: {duration_min} mins | Avg HR: {hr} | Coros Load: {coros_load}"
            )
            
        return "\n".join(history)
    except Exception as e:
        logger.error(f"❌ Strava Fetch Error: {e}")
        return "Could not fetch Strava history."