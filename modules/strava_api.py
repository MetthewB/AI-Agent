import re
import asyncio
import logging
import requests
import datetime

# Import Database tools
from modules.database import SessionLocal, Activity
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
# 2. DATABASE SYNC (PostgreSQL)
# ==========================================
async def sync_activities_to_db(activities_data):
    """
    Takes a list of activity dictionaries from Strava API 
    and persists new ones into PostgreSQL.
    """
    db = SessionLocal()
    new_count = 0
    
    try:
        for act in activities_data:
            strava_id = act.get('id')
            
            # Check if this activity already exists in our Long-Term Memory
            exists = db.query(Activity).filter(Activity.strava_id == strava_id).first()
            
            if not exists:
                # Convert Strava date string to Python datetime object
                date_str = act.get('start_date_local', '')[:10]
                date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.datetime.utcnow()
                
                # Extract Coros Load from description
                desc = act.get('description', '') or ''
                coros_load = None
                if "charge d'entraînement" in desc.lower():
                    match = re.search(r'(\d+)\s*charge', desc.lower())
                    if match:
                        coros_load = int(match.group(1))

                new_act = Activity(
                    strava_id=strava_id,
                    date=date_obj,
                    sport=act.get('sport_type') or act.get('type'),
                    distance=act.get('distance', 0) / 1000, # convert to km
                    duration=act.get('moving_time', 0) // 60, # convert to minutes
                    avg_hr=act.get('average_heartrate'),
                    coros_load=coros_load
                )
                db.add(new_act)
                new_count += 1
        
        db.commit()
        if new_count > 0:
            logger.info(f"📊 Database Sync: Added {new_count} new activities to PostgreSQL.")
    except Exception as e:
        logger.error(f"❌ Database Sync Error: {e}")
        db.rollback()
    finally:
        db.close()
    return new_count

# ==========================================
# 3. DATA FETCHING & FORMATTING
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

        # Trigger background sync to PostgreSQL
        await sync_activities_to_db(activities)
        
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
            if desc and "charge d'entraînement" in desc.lower():
                match = re.search(r'(\d+)\s*charge', desc.lower())
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