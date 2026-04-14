import asyncio
import logging
from huggingface_hub import AsyncInferenceClient

# Import the token from your new config module
from modules.config import HF_TOKEN

# Set up logging for this module
logger = logging.getLogger(__name__)

# ==========================================
# 1. INITIALIZE THE LLM CLIENT
# ==========================================
llm_client = AsyncInferenceClient(model="google/gemma-2-2b-it", token=HF_TOKEN)

# ==========================================
# 2. CORE INFERENCE FUNCTION
# ==========================================
async def ask_llm(prompt: str, max_tokens: int = 400) -> str:
    """Sends a prompt to the HuggingFace LLM asynchronously with a strict timeout."""
    try:
        logger.info(f"🧠 Sending prompt to LLM (Limit: {max_tokens})...")
        messages = [{"role": "user", "content": prompt}]
        
        # We use a 30-second timeout to prevent the bot from hanging if the API has a cold start
        response = await asyncio.wait_for(
            llm_client.chat_completion(messages=messages, max_tokens=max_tokens, temperature=0.7), 
            timeout=30.0
        )
        
        logger.info("✅ LLM response generated successfully.")
        return response.choices[0].message.content
        
    except asyncio.TimeoutError:
        logger.error("❌ LLM Error: Request timed out.")
        return "<i>My AI brain took too long to think! The servers are busy, please try again.</i>"
        
    except Exception as e:
        logger.error(f"❌ LLM Error: {e}")
        return "<i>Sorry, my AI brain is a bit foggy right now.</i>"