import requests
import logging
import asyncio
from modules.config import HF_TOKEN

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_URL = "https://router.huggingface.co/hf-inference/v1/embeddings"

async def generate_embedding(text: str):
    """Turns text into a 384-dimension vector using the modern v1 API."""
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}", 
        "Content-Type": "application/json"
    }
    payload = {
        "model": "sentence-transformers/all-MiniLM-L6-v2",
        "input": text
    }
    
    try:
        response = await asyncio.to_thread(
            requests.post, 
            EMBEDDING_MODEL_URL, 
            headers=headers, 
            json=payload, 
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            return result["data"][0]["embedding"]
        else:
            logger.error(f"❌ Embedding Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"❌ Embedding Exception: {e}")
        return None