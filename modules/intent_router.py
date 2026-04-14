import re
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
    grocery_remove_command, stats_command, cat_command, 
    dateidea_command, remind_command, research_command
)

logger = logging.getLogger(__name__)

# ==========================================
# The Natural Language Understanding Brain
# ==========================================
async def parse_intent(user_text: str) -> dict:
    """
    Analyzes raw text to determine which bot function to trigger.
    Returns a dictionary with 'action' and 'data'.
    """
    prompt = f"""
    [ROLE]
    You are an Intent Router for a Telegram Bot.
    
    [TASK]
    Analyze the user's message and categorize it into one of the following ACTIONS.
    If the message doesn't match an action, return ACTION: chat.

    [AVAILABLE ACTIONS]
    - grocery_add: User wants to add an item to the shopping list. (data = item)
    - grocery_remove: User wants to delete/remove an item from the list. (data = item)
    - grocery_list: User wants to see the current shopping list. (data = "")
    - weather: User is asking about the weather/temperature. (data = city)
    - train: User wants a workout or training plan. (data = sport/details)
    - portfolio: User wants to see stock/market prices. (data = "")
    - news: User wants a geopolitical news briefing. (data = "")
    - remind: User wants to set a timer or reminder. (data = "time message", e.g., "15m check oven")
    - cat: User wants a cat gif. (data = "")
    - research: User wants a deep dive or summary of a specific topic. (data = topic)
    - recipe: User wants a recipe based on ingredients. (data = ingredients)
    - dateidea: User wants a date idea. (data = city)
    - stats: User wants to see their weekly Strava stats. (data = "")
    - chat: General conversation or questions not covered above. (data = user's message)

    [USER MESSAGE]
    "{user_text}"

    [OUTPUT FORMAT]
    Return ONLY a JSON-style string: {{"action": "action_name", "data": "extracted_subject_or_query"}}
    """
    
    response = await ask_llm(prompt)
    try:
        clean_json = re.search(r'\{.*\}', response, re.DOTALL).group()
        return json.loads(clean_json)
    except Exception as e:
        logger.error(f"Intent Parse Error: {e} - Raw: {response}")
        return {"action": "chat", "data": user_text}


# ==========================================
# TEXT ROUTING HANDLER
# ==========================================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Intercepts standard text messages and routes them without needing /commands."""
    if not is_authorized(update): return
    
    user_text = update.message.text
    if not user_text: return

    # 1. Ask the Brain what the user wants
    intent = await parse_intent(user_text)
    action = intent.get("action")
    data = intent.get("data", "")

    logger.info(f"🧠 NLU Intent Detected: {action} | Data: {data}")

    # 2. Route to the correct existing command
    if action == "grocery_add":
        context.args = [data]
        await grocery_command(update, context)
        
    elif action == "grocery_remove":
        context.args = [data]
        await grocery_remove_command(update, context)
        
    elif action == "grocery_list":
        context.args = []
        await grocery_command(update, context)
        
    elif action == "weather":
        context.args = [data]
        await weather_command(update, context)
        
    elif action == "train":
        context.args = [data]
        await train_command(update, context)
        
    elif action == "portfolio":
        await portfolio_command(update, context)
        
    elif action == "news":
        await news_command(update, context)
        
    elif action == "cat":
        await cat_command(update, context)
        
    elif action == "stats":
        await stats_command(update, context)
        
    elif action == "recipe":
        context.args = data.split()
        await recipe_command(update, context)
        
    elif action == "research":
        context.args = [data]
        await research_command(update, context)
        
    elif action == "dateidea":
        context.args = [data]
        await dateidea_command(update, context)
        
    elif action == "remind":
        context.args = data.split(" ", 1)
        await remind_command(update, context)

    elif action == "chat":
        status_msg = await update.message.reply_text("<i>Thinking...</i>", parse_mode=ParseMode.HTML)
        response = await ask_llm(user_text)
        await status_msg.edit_text(response, parse_mode=ParseMode.HTML)


# ==========================================
# VOICE ROUTING HANDLER
# ==========================================
async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Transcribes voice notes and routes them as multiple parallel commands."""
    if not is_authorized(update): return
    logger.info(f"🎤 Voice message received from {update.effective_chat.id}")

    status_msg = await update.message.reply_text("🗣️ <i>Listening...</i>", parse_mode=ParseMode.HTML)

    try:
        # 1. Download the voice note
        voice_file = await update.message.voice.get_file()
        audio_bytes = await voice_file.download_as_bytearray()

        # 2. Transcribe using Whisper
        API_URL = "https://router.huggingface.co/hf-inference/models/openai/whisper-large-v3-turbo"
        headers = {
            "Authorization": f"Bearer {HF_TOKEN}",
            "Content-Type": "audio/ogg"
        }
        
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

        # 3. Route intent using the LLM (Voice can trigger MULTIPLE commands!)
        prompt = f"""
        You are a strict, highly logical API router. 
        Read this transcribed voice message: "{transcription}"
        
        Map the user's intent to one OR MORE of the available commands below.
        
        CRITICAL RULES:
        1. Extract ONLY the exact parameters needed.
        2. Detect language. Set "lang" to "fr" (French) or "en" (English).
        3. Unsupported languages -> set "command" to "unsupported_language".
        
        AVAILABLE COMMANDS & ARGUMENTS:
        - train: args = ["sport details"] 
        - weather: args = ["city"] 
        - news: args = [] 
        - portfolio: args = [] 
        - recipe: args = ["ingredient1 ingredient2"] 
        - grocery: args = [] (to view list) OR args = ["item"] (to add)
        - grocery_remove: args = ["item"]
        - stats: args = [] 
        - cat: args = [] 
        - dateidea: args = ["city"]
        - research: args = ["topic"]
        - remind: args = ["time", "message"] (e.g., ["15m", "check the oven"])
            
        Return ONLY a valid JSON list of dictionaries.
        
        EXAMPLE - "Quel est le temps à Lausanne et donne moi les infos":
        [
          {{"command": "weather", "args": ["Lausanne"], "lang": "fr"}},
          {{"command": "news", "args": [], "lang": "fr"}}
        ]
        """
        
        routing_response = await ask_llm(prompt, max_tokens=200)
        routing_response = routing_response.replace("```json", "").replace("```", "").strip()
        
        try:
            commands_to_run = json.loads(routing_response)
        except json.JSONDecodeError:
            logger.error(f"❌ JSON Parse Error from Voice LLM: {routing_response}")
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
            "dateidea": dateidea_command,
            "research": research_command,
            "remind": remind_command
        }

        # 4. Execute the commands
        for cmd in commands_to_run:
            cmd_name = cmd.get("command", "").replace("/", "")
            args = cmd.get("args", [])
            lang = cmd.get("lang", "en").lower()
            
            if cmd_name == "unsupported_language" or lang not in ["en", "fr"]:
                await update.message.reply_text("⚠️ <i>I only understand English and French! / Je ne comprends que l'anglais et le français !</i>", parse_mode=ParseMode.HTML)
                continue
            
            context.user_data["lang"] = lang
            
            if cmd_name in command_map:
                context.args = args 
                await command_map[cmd_name](update, context)
            else:
                await update.message.reply_text(f"⚠️ <i>Command '{cmd_name}' recognized by AI but not programmed yet.</i>", parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"❌ Voice Handler Error: {e}")
        await status_msg.edit_text("⚠️ <i>An error occurred while processing your voice.</i>", parse_mode=ParseMode.HTML)