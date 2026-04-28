import logging
from huggingface_hub import AsyncInferenceClient
from modules.config import HF_TOKEN

logger = logging.getLogger(__name__)

client = AsyncInferenceClient(token=HF_TOKEN)
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

async def generate_embedding(text: str):
    """Turns text into a 384-dimension vector using the official HF SDK."""
    try:
        response = await client.feature_extraction(
            text, 
            model=MODEL_NAME
        )
        
        if hasattr(response, "tolist"):
            embedding = response.tolist()
        else:
            embedding = list(response)
            
        if isinstance(embedding, list) and len(embedding) > 0 and isinstance(embedding[0], list):
            return embedding[0]
            
        return embedding
        
    except Exception as e:
        logger.error(f"❌ Embedding Exception: {e}")
        return None