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
    
    for attempt in range(3):
        try:
            logger.info(f"🧠 Asking AI (Attempt {attempt + 1}/3)...")
            response = await asyncio.to_thread(
                requests.post,
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=25
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                
                if not content or not content.strip():
                    logger.warning("⚠️ OpenRouter returned an empty string. Retrying...")
                    continue
                    
                if "User Safety:" in content:
                    logger.warning("⚠️ OpenRouter routed to a safety model. Retrying...")
                    continue
                    
                logger.info("✅ Success! Valid response received.")
                return content.strip()
                
            elif response.status_code == 429:
                logger.warning("⚠️ Rate limited (429). Retrying...")
            else:
                logger.error(f"❌ API Error {response.status_code}: {response.text}")

        except Exception as e:
            logger.warning(f"⚠️ Connection error: {e}. Retrying...")
            
        await asyncio.sleep(2)
        
    logger.error("❌ All AI attempts failed.")
    return "⚠️ L'IA est indisponible pour le moment. Veuillez réessayer plus tard."