import requests
import logging
from modules.config import HF_TOKEN

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_URL = "https://api-inference.huggingface.co/models/sentence-transformers/all-MiniLM-L6-v2"

async def generate_embedding(text: str):
    """Turns text into a 384-dimension vector."""
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {"inputs": text, "options": {"wait_for_model": True}}
    
    try:
        response = requests.post(EMBEDDING_MODEL_URL, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"❌ Embedding Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"❌ Embedding Exception: {e}")
        return None