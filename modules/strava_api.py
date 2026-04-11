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
    print("--- DEBUG 0: Entered sync_activities_to_db ---")
    print(f"DEBUG 0.5: activities_data is type: {type(activities_data)}")
    
    # 1. Catch API Error Responses (e.g. if Strava sent a dictionary with an error message instead of a list)
    if not isinstance(activities_data, list):
        print(f"DEBUG ERROR: Expected a list of activities, but got {type(activities_data)}: {activities_data}")
        return 0

    db = SessionLocal()
    new_count = 0
    
    try:
        print(f"DEBUG 1: Processing {len(activities_data)} activities from Strava")
        for index, act in enumerate(activities_data):
            print(f"\n--- DEBUG 2: Inspecting Activity [{index}] ---")
            
            # Extract ID safely
            strava_id = act.get('id')
            print(f"DEBUG 3: strava_id = {strava_id} (Type: {type(strava_id)})")
            
            if not strava_id:
                print("DEBUG 4: Skipping - No strava_id found in this activity.")
                continue
                
            # 2. Check if it exists
            print("DEBUG 5: Querying database for existence...")
            exists = db.query(Activity).filter(Activity.strava_id == strava_id).first()
            
            if exists:
                print(f"DEBUG 6: Activity {strava_id} ALREADY EXISTS. Skipping.")
            else:
                print(f"DEBUG 6: Activity {strava_id} is NEW. Attempting to parse data...")
                
                # 3. Inner Try/Except: If one activity has bad data, don't crash the whole sync!
                try:
                    # Safely handle dates
                    raw_date = act.get('start_date_local', '')
                    date_str = str(raw_date)[:10] if raw_date else ""
                    print(f"DEBUG 7a: Parsing date string: '{date_str}'")
                    
                    try:
                        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                    except Exception as date_err:
                        print(f"DEBUG 7b: Date parsing failed ({date_err}), falling back to utcnow.")
                        date_obj = datetime.datetime.utcnow()

                    # Safely handle numbers
                    sport = act.get('sport_type') or act.get('type', 'Unknown')
                    distance = float(act.get('distance', 0)) / 1000
                    duration = int(act.get('moving_time', 0)) // 60
                    avg_hr = act.get('average_heartrate')
                    
                    print(f"DEBUG 8: Parsed stats -> Sport: {sport}, Dist: {distance}, Dur: {duration}, HR: {avg_hr}")

                    new_act = Activity(
                        strava_id=strava_id,
                        date=date_obj,
                        sport=sport,
                        distance=distance,
                        duration=duration,
                        avg_hr=avg_hr,
                        coros_load=None # Skipping Coros regex temporarily to isolate bugs
                    )
                    
                    print("DEBUG 9: Adding to DB session...")
                    db.add(new_act)
                    new_count += 1
                    
                except Exception as inner_e:
                    print(f"DEBUG ERROR INNER: Failed to process activity {strava_id}. Reason: {inner_e}")
                    # Notice we do NOT raise here, so it continues to the next activity
        
        print(f"\n--- DEBUG 10: Loop finished. Attempting to commit {new_count} new items... ---")
        db.commit()
        print("DEBUG 11: Commit successful!")
        
        if new_count > 0:
            logger.info(f"📊 PostgreSQL Sync: Saved {new_count} new activities.")
            
    except Exception as e:
        print(f"DEBUG ERROR OUTER: CRITICAL DATABASE CRASH: {e}")
        logger.error(f"❌ PostgreSQL Sync Error: {e}")
        db.rollback()
    finally:
        db.close()
        print("DEBUG 12: Database session closed.\n")
        
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