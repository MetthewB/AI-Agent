import requests
import logging
import asyncio
from modules.config import OPENROUTER_API_KEY_BOT

logger = logging.getLogger(__name__)

FREE_MODELS = [
    "google/gemma-4-31b-it:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-8b:free",
    "mistralai/mistral-7b-instruct:free",
    "nousresearch/deephermes-3-llama-3-8b:free",
]

async def ask_llm(prompt: str, max_tokens: int = 800) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY_BOT}",
        "Content-Type": "application/json"
    }

    for model in FREE_MODELS:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": max_tokens
        }
        
        try:
            logger.info(f"🧠 Asking AI ({model})...")
            response = await asyncio.to_thread(
                requests.post,
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=25
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                if content and content.strip():
                    return content.strip()
                logger.warning(f"⚠️ {model} returned empty content. Trying next...")
            elif response.status_code == 429:
                logger.warning(f"⚠️ {model} rate limited (429). Trying next...")
            elif response.status_code == 400:
                logger.warning(f"⚠️ {model} bad request (400) — likely not a free model. Trying next...")
            else:
                logger.warning(f"⚠️ {model} failed (HTTP {response.status_code}). Trying next...")
                
        except Exception as e:
            logger.warning(f"⚠️ Connection error with {model}: {e}. Trying next...")
            
    logger.error("❌ ALL models are currently offline or rate limited.")
    return None