import asyncio
import logging
import httpx
from modules.config import GOOGLE_API_KEY

logger = logging.getLogger(__name__)

# ==========================================
# CORE INFERENCE FUNCTION (Google AI Studio)
# ==========================================
async def ask_llm(prompt: str, max_tokens: int = 400) -> str:
    """Sends a prompt to Google AI Studio with automatic retries for 503 errors."""
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GOOGLE_API_KEY}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens, 
            "temperature": 0.7
        }
    }

    max_retries = 3
    base_delay = 5.0

    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries):
            try:
                logger.info(f"🧠 Sending prompt to Gemini (Limit: {max_tokens}, Attempt: {attempt + 1}/{max_retries})...")
                res = await client.post(url, json=payload, timeout=30.0)
                res.raise_for_status() 
                
                logger.info("✅ LLM response generated successfully.")
                raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
                clean = raw_text.replace("*", "").replace("#", "").replace("`", "").replace("<", "").replace(">", "")

                return clean.strip()
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code in [503, 429]:
                    logger.warning(f"⚠️ Google API busy ({e.response.status_code}). Retrying in {base_delay}s...")
                    await asyncio.sleep(base_delay)
                    continue
                else:
                    logger.error(f"❌ Google API HTTP Error: {e.response.text}")
                    return "<i>Sorry, my AI brain hit a roadblock.</i>"
                    
            except httpx.TimeoutException:
                logger.error("❌ LLM Error: Request timed out.")
                return "<i>My AI brain took too long to think! The servers are busy.</i>"
                
            except Exception as e:
                logger.error(f"❌ General LLM Error: {e}")
                return "<i>Sorry, my AI brain is a bit foggy right now.</i>"

        return "<i>Google's servers are completely overloaded right now. Give me a minute to breathe! 🚦</i>"