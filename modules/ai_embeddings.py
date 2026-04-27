import requests
import logging
import asyncio
from modules.config import HF_TOKEN

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_URL = "https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/all-MiniLM-L6-v2"

async def generate_embedding(text: str):
    """Turns text into a 384-dimension vector."""
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}", 
        "Content-Type": "application/json"
    }
    payload = {"inputs": text}
    
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
            if isinstance(result, list):
                if len(result) > 0 and isinstance(result[0], list):
                    return result[0]
                return result
            return result
        else:
            logger.error(f"❌ Embedding Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"❌ Embedding Exception: {e}")
        return None