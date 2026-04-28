import requests
import logging
import asyncio
from modules.config import OPENROUTER_API_KEY

logger = logging.getLogger(__name__)

async def ask_llm(prompt: str, max_tokens: int = 500) -> str:
    """
    Sends a prompt to OpenRouter.
    Uses an automatic fallback chain so the bot never crashes if a free model goes offline.
    """
    
    MODELS_TO_TRY = [
        "google/gemma-4-31b-it:free",          # Let's keep trying the smart one first
        "huggingfaceh4/zephyr-7b-beta:free",   # Highly stable backup
        "mistralai/mistral-7b-instruct:free",  # Very reliable free endpoint
        "openrouter/auto"                      # The ultimate fallback (OpenRouter picks a free one)
    ]
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    for model in MODELS_TO_TRY:
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
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
                timeout=20
            )
            
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]
            else:
                logger.warning(f"⚠️ Model {model} failed (HTTP {response.status_code}). Trying next...")
                continue
                
        except Exception as e:
            logger.warning(f"⚠️ Connection error with {model}: {e}. Trying next...")
            continue
            
    logger.error("❌ ALL free models are currently offline.")
    return None