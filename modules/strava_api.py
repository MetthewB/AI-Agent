import re
import asyncio
import logging
import requests

from modules.database import save_activity
from modules.config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN

logger = logging.getLogger(__name__)

# ==========================================
# HELPERS
# ==========================================
def extract_coros_load(description: str):
    """Extracts the Coros training load number from an activity description."""
    if not description:
        return None
    match = re.search(r'(\d+)\s*charge', description.lower())
    return int(match.group(1)) if match else None

# ==========================================
# AUTHENTICATION
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
        res = await asyncio.to_thread(requests.post, url, data=payload, timeout=10)
        return res.json().get("access_token")
    except Exception as e:
        logger.error(f"❌ Strava Token Error: {e}")
        return None

# ==========================================
# DATABASE SYNC (MongoDB)
# ==========================================
async def sync_activities_to_db(activities_data):
    """
    Takes a list of activity dictionaries from Strava API 
    and persists them into MongoDB using Upsert.
    """
    if not isinstance(activities_data, list):
        logger.error(f"❌ Sync Error: Expected a list of activities, got {type(activities_data)}")
        return 0

    new_count = 0
    
    try:
        for act in activities_data:
            strava_id = act.get('id')
            if not strava_id:
                continue
                
            sport = act.get('sport_type') or act.get('type', 'Unknown')
            distance = float(act.get('distance', 0)) / 1000
            duration = int(act.get('moving_time', 0)) // 60
            avg_hr = act.get('average_heartrate')
            coros_load = extract_coros_load(act.get('description', ''))

            await save_activity(
                strava_id=strava_id,
                sport=sport,
                distance_km=distance,
                duration_min=duration,
                coros_load=coros_load,
                avg_hr=avg_hr
            )
            new_count += 1
        
        if new_count > 0:
            logger.info(f"📊 MongoDB Sync: Processed {new_count} activities.")
            
    except Exception as e:
        logger.error(f"❌ MongoDB Sync Error: {e}")
        
    return new_count

# ==========================================
# DATA FETCHING & FORMATTING
# ==========================================
async def get_recent_strava_activities(limit: int = 5) -> str:
    """Fetches latest activities, syncs them to DB, and returns a formatted string."""
    access_token = await get_strava_access_token()
    if not access_token: 
        return "No Strava data available."
    
    url = f"https://www.strava.com/api/v3/athlete/activities?per_page={limit}"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        res = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
        activities = res.json()
        
        if not activities or not isinstance(activities, list): 
            return "No recent history."

        await sync_activities_to_db(activities)
        
        history = []
        for act in activities:
            name = act.get('name', 'Workout')
            desc = act.get('description', '') or ''
            date_str = act.get('start_date_local', 'Unknown Date')[:10]
            dist = act.get('distance', 0) / 1000
            duration_min = int(act.get('moving_time', 0)) // 60
            hr = act.get('average_heartrate', 'N/A')
            coros_load = extract_coros_load(desc) or "Unknown"

            history.append(
                f"- {date_str} | Title: '{name}' | Dist: {dist:.1f}km | "
                f"Duration: {duration_min} mins | Avg HR: {hr} | Coros Load: {coros_load}"
            )
            
        return "\n".join(history)
    except Exception as e:
        logger.error(f"❌ Strava Fetch Error: {e}")
        return "Could not fetch Strava history."