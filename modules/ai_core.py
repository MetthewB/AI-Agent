import asyncio
import logging
import httpx
from modules.config import OPENROUTER_API_KEY

logger = logging.getLogger(__name__)

async def ask_llm(prompt: str, max_tokens: int = 400) -> str:
    """Sends prompt exclusively to the premium Qwen 2.5 72B model."""
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "qwen/qwen-2.5-72b-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7
    }

    max_retries = 3
    base_delay = 5.0

    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries):
            try:
                logger.info(f"🧠 Sending prompt to Qwen 72B (Limit: {max_tokens}, Attempt: {attempt + 1}/{max_retries})...")
                res = await client.post(url, headers=headers, json=payload, timeout=30.0)
                res.raise_for_status() 
                
                raw_text = res.json().get('choices', [{}])[0].get('message', {}).get('content', '')
                
                if raw_text is None:
                    raw_text = ""
                
                clean = raw_text.replace("*", "").replace("#", "").replace("`", "").replace("<", "").replace(">", "")

                return clean.strip() if clean.strip() else "<i>My brain generated an empty response.</i>"
                
            except httpx.HTTPStatusError as e:
                # 503 (Busy) or 429 (Rate Limit)
                if e.response.status_code in [503, 429]:
                    logger.warning(f"⚠️ API busy ({e.response.status_code}). Retrying in {base_delay}s...")
                    await asyncio.sleep(base_delay)
                    continue
                # 402 (Insufficient Funds)
                elif e.response.status_code == 402:
                    logger.error("❌ OpenRouter Error: Insufficient funds. Please top up your account.")
                    return "<i>My OpenRouter account is out of credits! Please top up. 💳</i>"
                else:
                    logger.error(f"❌ OpenRouter API HTTP Error: {e.response.text}")
                    return "<i>Sorry, my AI brain hit a roadblock.</i>"
                    
            except httpx.TimeoutException:
                logger.error("❌ LLM Error: Request timed out.")
                return "<i>My AI brain took too long to think! The servers are busy.</i>"
                
            except Exception as e:
                logger.error(f"❌ General LLM Error: {e}")
                return "<i>Sorry, my AI brain is a bit foggy right now.</i>"

        return "<i>The AI servers are completely overloaded right now. Give me a minute to breathe! 🚦</i>"