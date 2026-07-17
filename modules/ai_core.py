import requests
import logging
import asyncio
from modules.config import OPENROUTER_API_KEY_BOT

logger = logging.getLogger(__name__)

async def ask_llm(prompt: str, max_tokens: int = 800) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY_BOT}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "openrouter/free", 
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": max_tokens
    }
    
    try:
        logger.info("🧠 Asking AI")
        response = await asyncio.to_thread(
            requests.post,
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=25
        )
        
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            model_used = response.json().get("model", "unknown free model")
            
            if content and content.strip():
                logger.info(f"✅ Success! Routed to: {model_used}")
                return content.strip()
            
            logger.warning("⚠️ OpenRouter returned an empty string.")
        
        elif response.status_code == 429:
             logger.error("❌ Global rate limit hit for OpenRouter's free tier. Try again later.")
        else:
            logger.error(f"❌ OpenRouter API failed with status {response.status_code}: {response.text}")
            
    except Exception as e:
        logger.error(f"❌ Connection error with OpenRouter: {e}")
        
    return None