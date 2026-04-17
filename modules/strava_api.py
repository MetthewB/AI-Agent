import re
import asyncio
import logging
import requests
import datetime

from modules.database import SessionLocal, Activity
from modules.config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN

logger = logging.getLogger(__name__)

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
# DATABASE SYNC (PostgreSQL)
# ==========================================
async def sync_activities_to_db(activities_data):
    """
    Takes a list of activity dictionaries from Strava API 
    and persists new ones into PostgreSQL.
    """
    if not isinstance(activities_data, list):
        logger.error(f"❌ Sync Error: Expected a list of activities, got {type(activities_data)}")
        return 0

    db = SessionLocal()
    new_count = 0
    
    try:
        for act in activities_data:
            strava_id = act.get('id')
            if not strava_id:
                continue
                
            exists = db.query(Activity).filter(Activity.strava_id == strava_id).first()
            
            if not exists:
                try:
                    raw_date = act.get('start_date_local', '')
                    date_str = str(raw_date)[:10] if raw_date else ""
                    
                    try:
                        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                    except Exception:
                        date_obj = datetime.datetime.utcnow()

                    sport = act.get('sport_type') or act.get('type', 'Unknown')
                    distance = float(act.get('distance', 0)) / 1000
                    duration = int(act.get('moving_time', 0)) // 60
                    avg_hr = act.get('average_heartrate')

                    new_act = Activity(
                        strava_id=strava_id,
                        date=date_obj,
                        sport=sport,
                        distance=distance,
                        duration=duration,
                        avg_hr=avg_hr,
                        coros_load=None
                    )
                    
                    db.add(new_act)
                    new_count += 1
                    
                except Exception as inner_e:
                    logger.error(f"❌ Failed to process activity {strava_id}. Reason: {inner_e}")
        
        db.commit()
        
        if new_count > 0:
            logger.info(f"📊 PostgreSQL Sync: Saved {new_count} new activities.")
            
    except Exception as e:
        logger.error(f"❌ PostgreSQL Sync Error: {e}")
        db.rollback()
    finally:
        db.close()
        
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
            moving_time_sec = act.get('moving_time', 0)
            duration_min = moving_time_sec // 60
            
            hr = act.get('average_heartrate', 'N/A')
            
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