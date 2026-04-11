from fastapi import FastAPI, Request, HTTPException, Query
import logging
import asyncio

# Import your existing logic!
from modules.strava_api import sync_activities_to_db, get_strava_access_token
import requests

logger = logging.getLogger(__name__)
app = FastAPI()

# 🔐 You invent this token. It acts as a password between you and Strava.
STRAVA_VERIFY_TOKEN = "matthieu_strava_secret_2026" 

# ==========================================
# 1. THE HANDSHAKE (Validation)
# ==========================================
@app.get("/strava/webhook")
async def verify_strava_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    """Strava uses this to verify you own the server."""
    if hub_mode == "subscribe" and hub_verify_token == STRAVA_VERIFY_TOKEN:
        logger.info("✅ Strava Webhook Successfully Verified!")
        # You MUST return exactly this JSON to complete the handshake
        return {"hub.challenge": hub_challenge}
    
    raise HTTPException(status_code=403, detail="Invalid verification token")

# ==========================================
# 2. THE FIREHOSE (Receiving Events)
# ==========================================
@app.post("/strava/webhook")
async def receive_strava_event(request: Request):
    """Strava sends workout data here the moment you finish a run."""
    event_data = await request.json()
    logger.info(f"🚨 Webhook Triggered! Data: {event_data}")
    
    # 🏃‍♂️ Check if it's a brand NEW activity
    if event_data.get("object_type") == "activity" and event_data.get("aspect_type") == "create":
        activity_id = event_data.get("object_id")
        logger.info(f"🏃‍♂️ New workout saved on Strava! ID: {activity_id}")
        
        # ⚠️ We use asyncio.create_task so FastAPI can reply to Strava instantly
        # If you take longer than 2 seconds, Strava will think your server is dead.
        asyncio.create_task(process_new_workout(activity_id))
        
    return {"status": "success"}

# ==========================================
# 3. THE PROCESSING LOGIC
# ==========================================
async def process_new_workout(activity_id: int):
    """Fetches the new workout, saves it to Postgres, and tells the AI."""
    try:
        # 1. Get Token
        access_token = await get_strava_access_token()
        
        # 2. Fetch the specific new activity from Strava
        url = f"https://www.strava.com/api/v3/activities/{activity_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        res = await asyncio.to_thread(requests.get, url, headers=headers)
        
        if res.status_code == 200:
            activity_data = res.json()
            
            # 3. Save it to your PostgreSQL Long-Term Memory!
            # Note: Our sync function expects a list, so we put the single dict in a list
            await sync_activities_to_db([activity_data])
            
            # 4. Trigger LangGraph / Telegram Notification here!
            logger.info("✅ New workout synced from Webhook!")
            # await send_telegram_message(f"Just logged your {activity_data['distance']/1000}km run to the DB!")
            
    except Exception as e:
        logger.error(f"❌ Error processing webhook activity: {e}")