import logging
import httpx
from modules.config import GOOGLE_API_KEY

logger = logging.getLogger(__name__)

# ==========================================
# CORE INFERENCE FUNCTION (Google AI Studio)
# ==========================================
async def ask_llm(prompt: str, max_tokens: int = 400) -> str:
    """Sends a prompt to Google AI Studio (Gemma 4) asynchronously."""
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemma-4-e2b-it:generateContent?key={GOOGLE_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens, 
            "temperature": 0.7
        }
    }

    logger.info(f"🧠 Sending prompt to Google AI Studio (Limit: {max_tokens})...")

    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(url, json=payload, timeout=30.0)
            res.raise_for_status()
            
            logger.info("✅ LLM response generated successfully.")
            
            return res.json()['candidates'][0]['content']['parts'][0]['text']
            
        except httpx.TimeoutException:
            logger.error("❌ LLM Error: Request timed out.")
            return "<i>My AI brain took too long to think! The servers are busy, please try again.</i>"
            
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Google API HTTP Error: {e.response.text}")
            return "<i>Sorry, my AI brain hit a roadblock.</i>"
            
        except Exception as e:
            logger.error(f"❌ General LLM Error: {e}")
            return "<i>Sorry, my AI brain is a bit foggy right now.</i>"