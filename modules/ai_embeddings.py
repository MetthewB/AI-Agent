import logging
import asyncio
from huggingface_hub import AsyncInferenceClient
from modules.config import HF_TOKEN

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

MAX_RETRIES = 3
BASE_DELAY = 2

async def generate_embedding(text: str):
    """
    Turns text into a 384-dimension vector using HuggingFace inference.
    Retries up to 3 times with exponential backoff on gateway errors.
    """
    client = AsyncInferenceClient(token=HF_TOKEN, timeout=15)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.debug(f"🔢 Embedding attempt {attempt}/{MAX_RETRIES}...")
            response = await client.feature_extraction(text, model=MODEL_NAME)

            if hasattr(response, "tolist"):
                embedding = response.tolist()
            else:
                embedding = list(response)

            if isinstance(embedding, list) and len(embedding) > 0 and isinstance(embedding[0], list):
                return embedding[0]

            return embedding

        except Exception as e:
            is_last_attempt = attempt == MAX_RETRIES
            is_gateway_error = "504" in str(e) or "502" in str(e) or "503" in str(e)

            if is_last_attempt:
                logger.error(f"❌ Embedding failed after {MAX_RETRIES} attempts: {e}")
                return None

            delay = BASE_DELAY ** attempt
            if is_gateway_error:
                logger.warning(f"⚠️ Gateway error (attempt {attempt}/{MAX_RETRIES}). Retrying in {delay}s...")
            else:
                logger.warning(f"⚠️ Embedding error (attempt {attempt}/{MAX_RETRIES}): {e}. Retrying in {delay}s...")

            await asyncio.sleep(delay)

    return None