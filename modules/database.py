import os
import logging
import datetime
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)
MONGO_URI = os.environ.get("MONGO_URI")

_client = None


def get_db():
    """Lazy initialization: Only creates the client if it doesn't exist yet,
    guaranteeing it attaches to the active Telegram event loop."""
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URI)
    return _client.mattoubot


async def init_db():
    """Pings the database and creates unique indexes to prevent duplicate data."""
    try:
        db = get_db()
        await db.client.admin.command('ping')
        
        await db.activities.create_index("strava_id", unique=True)
        await db.users.create_index("user_id", unique=True)
        
        logger.info("✅ MongoDB Connected and Indexes Initialized Successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to connect to MongoDB: {e}")


async def save_activity(strava_id: int, sport: str, distance_km: float, duration_min: int, coros_load: int = None, avg_hr: float = None):
    """Upserts a Strava activity into the database."""
    db = get_db()
    activity_doc = {
        "strava_id": strava_id,
        "date": datetime.datetime.utcnow(),
        "sport": sport,
        "distance": distance_km,
        "duration": duration_min,
        "coros_load": coros_load,
        "avg_hr": avg_hr
    }
    
    await db.activities.update_one(
        {"strava_id": strava_id},
        {"$set": activity_doc},
        upsert=True
    )


async def get_user_language(user_id: int) -> str:
    """Fetches the user's saved language, defaults to English."""
    db = get_db()
    user = await db.users.find_one({"user_id": user_id})
    if user and "language" in user:
        return user["language"]
    return "en"


async def update_user_language(user_id: int, language: str):
    """Updates the user's preferred language and last active timestamp."""
    db = get_db()
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "language": language,
            "last_active": datetime.datetime.utcnow()
        }},
        upsert=True
    )