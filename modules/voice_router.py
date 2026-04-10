import json
import asyncio
import logging
import requests
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

# Import config and core AI functions
from modules.config import HF_TOKEN
from modules.ai_core import ask_llm

# Import all the commands we need to trigger
from modules.commands import (
    is_authorized, train_command, weather_command, news_command,
    portfolio_command, recipe_command, grocery_command,
    grocery_remove_command, stats_command, cat_command, dateidea_command
)

# Set up logging
logger = logging.getLogger(__name__)

# ==========================================
# VOICE & ROUTING HANDLER
# ==========================================
async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"🎤 Voice message received from {update.effective_chat.id}")

    status_msg = await update.message.reply_text("🗣️ <i>Listening...</i>", parse_mode=ParseMode.HTML)

    try:
        # 1. Download the voice note (Telegram uses .ogg format)
        voice_file = await update.message.voice.get_file()
        audio_bytes = await voice_file.download_as_bytearray()

        # 2. Transcribe using Hugging Face's Free Whisper Model
        API_URL = "https://router.huggingface.co/hf-inference/models/openai/whisper-large-v3-turbo"
        headers = {
            "Authorization": f"Bearer {HF_TOKEN}",
            "Content-Type": "audio/ogg"
        }
        
        # We send the raw bytes directly to the API
        res = await asyncio.to_thread(requests.post, API_URL, headers=headers, data=audio_bytes, timeout=20)
        
        if res.status_code != 200:
            logger.error(f"Whisper API Error: {res.text}")
            await status_msg.edit_text("⚠️ <i>My ears are clogged (Whisper API error). Try typing!</i>", parse_mode=ParseMode.HTML)
            return
            
        transcription = res.json().get("text", "").strip()

        if not transcription:
            await status_msg.edit_text("⚠️ <i>I couldn't hear anything clearly. Could you speak up?</i>", parse_mode=ParseMode.HTML)
            return

        await status_msg.edit_text(f"🗣️ <b>You said:</b> <i>\"{transcription}\"</i>\n🧠 <i>Routing commands...</i>", parse_mode=ParseMode.HTML)

        # 3. Route intent using Qwen
        prompt = f"""
        You are a strict, highly logical API router. 
        Read this transcribed voice message (it may be in French or English): "{transcription}"
        
        Map the user's intent to one OR MORE of the available commands below.
        
        CRITICAL RULES FOR ARGS & LANGUAGE:
        1. Extract ONLY the exact parameters needed. Do NOT include filler words or full sentences.
        2. Detect the language of the transcription. Set the "lang" key to "fr" for French, or "en" for English.
        3. IF THE TRANSCRIPTION IS IN SPANISH, GERMAN, ITALIAN, OR ANY OTHER LANGUAGE, set "command" to "unsupported_language" and leave args empty.
        
        AVAILABLE COMMANDS & ARGUMENT RULES:
        - train: args = ["sport", "details"] (e.g., ["running", "10km easy"])
        - weather: args = ["city"] (e.g., ["Paris"] - ONLY the city name!)
        - news: args = [] (No args)
        - portfolio: args = [] (No args)
        - recipe: args = ["ingredient1", "ingredient2"] 
        - grocery: 
            - If they ask to READ, CHECK, or SEE the list: args = [] (Must be empty!)
            - If they ask to ADD an item to the list: args = ["item name"]
        - grocery_remove: 
            - If they ask to REMOVE, DELETE, or TAKE OFF an item: args = ["item name"]
        - stats: args = [] (No args)
        - cat: args = [] (No args)
        - dateidea: args = ["city"] (e.g., ["Geneva"])
            
        Return ONLY a valid JSON list of dictionaries. No markdown formatting, no explanation, no extra text.
        
        EXAMPLE 1 - "Quel est le temps à Lausanne et donne moi les infos":
        [
          {{"command": "weather", "args": ["Lausanne"], "lang": "fr"}},
          {{"command": "news", "args": [], "lang": "fr"}}
        ]
        
        EXAMPLE 2 - "Remove eggs from the grocery list":
        [
          {{"command": "grocery_remove", "args": ["eggs"], "lang": "en"}}
        ]
        """
        
        routing_response = await ask_llm(prompt, max_tokens=200)
        
        # Clean up in case the LLM tries to wrap the JSON in markdown blocks
        routing_response = routing_response.replace("```json", "").replace("```", "").strip()
        
        try:
            commands_to_run = json.loads(routing_response)
        except json.JSONDecodeError:
            logger.error(f"❌ JSON Parse Error from LLM: {routing_response}")
            await status_msg.edit_text("⚠️ <i>I understood the words, but my brain failed to map the commands!</i>", parse_mode=ParseMode.HTML)
            return

        if not commands_to_run:
            await status_msg.edit_text(f"🗣️ <b>You said:</b> <i>\"{transcription}\"</i>\n💬 I heard you, but I didn't detect any specific commands to run!", parse_mode=ParseMode.HTML)
            return

        await status_msg.delete()
        
        # Map strings to your actual Python functions
        command_map = {
            "train": train_command,
            "weather": weather_command,
            "news": news_command,
            "portfolio": portfolio_command,
            "recipe": recipe_command,
            "grocery": grocery_command,
            "grocery_remove": grocery_remove_command,
            "stats": stats_command,
            "cat": cat_command,
            "dateidea": dateidea_command
        }

        # 5. Execute the commands!
        for cmd in commands_to_run:
            cmd_name = cmd.get("command", "").replace("/", "")
            
            # Reject wrong languages immediately
            if cmd_name == "unsupported_language":
                await update.message.reply_text("⚠️ <i>I only understand English and French! / Je ne comprends que l'anglais et le français !</i>", parse_mode=ParseMode.HTML)
                continue
                
            args = cmd.get("args", [])
            lang = cmd.get("lang", "en")
            
            # Save their language preference so subsequent typed commands stay in the same language!
            context.user_data["lang"] = lang
            
            if cmd_name in command_map:
                context.args = args 
                await command_map[cmd_name](update, context)
            else:
                await update.message.reply_text(f"⚠️ <i>Command '{cmd_name}' recognized by AI but not programmed yet.</i>", parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"❌ Voice Handler Error: {e}")
        await status_msg.edit_text("⚠️ <i>An error occurred while processing your voice.</i>", parse_mode=ParseMode.HTML)