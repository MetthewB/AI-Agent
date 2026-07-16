import os
import asyncio
import logging
import datetime
from motor.motor_asyncio import AsyncIOMotorClient
    
from modules.ai_embeddings import generate_embedding

logger = logging.getLogger(__name__)
MONGO_URI = os.environ.get("MONGO_URI")

_loop_clients = {}


def get_db():
    """
    Retrieves the MongoDB database instance.
    Guarantees the client is attached to the CURRENTLY RUNNING event loop.
    """
    global _loop_clients
    
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return AsyncIOMotorClient(MONGO_URI).mattoubot

    if loop not in _loop_clients:
        logger.info(f"🌐 Creating new MongoDB client for event loop: {id(loop)}")
        _loop_clients[loop] = AsyncIOMotorClient(MONGO_URI)
        
    return _loop_clients[loop].mattoubot


async def init_db():
    """Pings the database to verify connection."""
    try:
        db = get_db()
        await db.command('ping')
        await db.activities.create_index("strava_id", unique=True)
        await db.users.create_index("user_id", unique=True)
        logger.info("✅ MongoDB Connected and Indexes Verified.")
    except Exception as e:
        logger.error(f"❌ Failed to connect to MongoDB: {e}")


async def add_to_vault(user_id: int, content: str, metadata: dict = None):
    """Generates embedding and saves a new memory to the vault."""
    
    vector = await generate_embedding(content)
    if not vector:
        logger.error("❌ Could not save to vault: Embedding generation failed.")
        return False
        
    db = get_db()
    document = {
        "user_id": user_id,
        "content": content,
        "embedding": vector,
        "timestamp": datetime.datetime.utcnow(),
        "metadata": metadata or {}
    }
    
    await db.vault.insert_one(document)
    logger.info(f"🧠 Memory saved to vault for user {user_id}")
    return True


async def search_vault(user_id: int, query_text: str, limit: int = 3) -> str:
    """
    Searches the vault for memories related to the user's query using Vector Search.
    Returns a formatted string of memories to be injected into the LLM prompt.
    """    
    query_vector = await generate_embedding(query_text)
    if not query_vector:
        logger.error("❌ Vector search failed: Could not generate query embedding.")
        return ""
        
    db = get_db()
    
    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index", 
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": limit * 10,
                "limit": limit,
                "filter": {"user_id": {"$eq": user_id}} 
            }
        },
        {
            "$project": {
                "_id": 0,
                "content": 1,
                "timestamp": 1,
                "score": { "$meta": "vectorSearchScore" }
            }
        }
    ]
    
    try:
        cursor = db.vault.aggregate(pipeline)
        results = await cursor.to_list(length=limit)
        
        if not results:
            return ""
            
        context_pieces = []
        for doc in results:
            score = doc.get("score", 0)
            if score > 0.5: 
                date_str = doc.get("timestamp").strftime("%Y-%m-%d") if doc.get("timestamp") else "Unknown date"
                context_pieces.append(f"- On {date_str}, user noted: {doc.get('content')}")
            
        return "\n".join(context_pieces)
        
    except Exception as e:
        logger.error(f"❌ Atlas Vector Search Exception: {e}")
        return ""


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