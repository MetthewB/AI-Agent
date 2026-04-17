import re
import html
import json
import asyncio
import logging
import requests
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from modules.ai_core import ask_llm
from modules.config import HF_TOKEN
from modules.utils import is_authorized

from commands.finance_news import portfolio_command, news_command
from commands.knowledge_util import research_command, weather_command, remind_command
from commands.shared_life import grocery_command, grocery_remove_command, recipe_command, decide_command
from commands.health_fitness import train_command, stats_command
from commands.fun_extras import movie_command, music_command, book_command, cat_command, dateidea_command

logger = logging.getLogger(__name__)

# ==========================================
# The Natural Language Understanding Brain
# ==========================================
async def parse_intent(user_text: str) -> list:
    """
    Analyzes raw text to determine which bot functions to trigger.
    Returns a LIST of dictionaries with 'action' and 'data'.
    """
    prompt = f"""
    [ROLE]
    You are a world-class NLU (Natural Language Understanding) routing engine. 
    Your job is to decipher user intent, extract necessary parameters, and map them to strict system actions.

    [CORE RULES]
    1. TYPO TOLERANCE: Aggressively autocorrect intent in your mind.
    2. SEMANTIC MATCHING: Look for the *meaning* behind the words, not just exact keywords.
    3. MEDIA VS RESEARCH: If asking for something to watch, read, or listen to, ALWAYS route to movie, book, or music.
    4. THE "CHAT" FALLBACK: Only use the "chat" action if the message is purely conversational.
    5. COMPOUND INTENTS: If the user asks to do multiple distinct things (e.g., "ajoute beurre et enlève yaourt" or "météo Paris et ajoute lait"), you MUST break them down into MULTIPLE objects in the JSON array.

    [ACTION DICTIONARY]
    Format -> action_name: [Trigger description] -> Data Payload

    --- LISTS & FOOD ---
    - grocery_add: User wants to add/buy an item. -> data: "the specific item"
    - grocery_remove: User wants to remove/delete/cross off an item. -> data: "the specific item"
    - grocery_list: User wants to see/read the current shopping list. -> data: ""
    - recipe: User wants cooking ideas or recipes based on items. -> data: "the ingredients"
    - decide: User wants to choose between options (e.g., "tacos pizza", "A ou B"). -> data: "option1 | option2 | option3"

    --- DATA & INFO ---
    - weather: User asks about temperature or forecasts. -> data: "city name"
    - portfolio: User asks about stocks, markets, investments. -> data: ""
    - news: User asks for global news, geopolitics. -> data: ""
    - research: User asks for factual deep dives or status updates. -> data: "the topic"

    --- HEALTH & LIFESTYLE ---
    - train: User wants a workout or training plan. -> data: "sport and details"
    - stats: User wants to see their Strava or workouts. -> data: ""
    - dateidea: User wants a romantic plan or date idea. -> data: "city name"

    --- UTILITIES & FUN ---
    - remind: User wants a timer or reminder. -> data: "time + message"
    - cat: User wants a cat gif. -> data: ""
    - music: User wants a song or playlist recommendation. -> data: "the vibe or genre"
    - movie: User wants a movie or series recommendation. -> data: "the genre or vibe"
    - book: User wants a book or novel recommendation. -> data: "the topic or vibe"
    
    --- FALLBACK ---
    - chat: General greetings or abstract questions. -> data: "the original user text"

    [USER MESSAGE]
    "{user_text}"

    [OUTPUT STRICT FORMAT]
    You must output ONLY a valid JSON array of objects. No explanations.
    [
      {{"action": "exact_action_name", "data": "extracted_string"}}
    ]
    """
    
    response = await ask_llm(prompt)
    try:
        clean_json = re.search(r'\[.*\]', response, re.DOTALL).group()
        return json.loads(clean_json)
    except Exception as e:
        logger.error(f"Intent Parse Error: {e} - Raw: {response}")
        return [{"action": "chat", "data": user_text}]


# ==========================================
# TEXT ROUTING HANDLER
# ==========================================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Intercepts standard text messages and routes them without needing /commands."""
    if not is_authorized(update): return
    
    user_text = update.message.text
    if not user_text: return

    intents = await parse_intent(user_text)

    for intent in intents:
        action = intent.get("action")
        data = intent.get("data", "")

        logger.info(f"🧠 NLU Intent Detected: {action} | Data: {data}")

        if action == "grocery_add":
            context.args = [data]
            await grocery_command(update, context)
            
        elif action == "grocery_remove":
            context.args = [data]
            await grocery_remove_command(update, context)
            
        elif action == "grocery_list":
            context.args = []
            await grocery_command(update, context)

        elif action == "movie":
            context.args = data.split()
            await movie_command(update, context)

        elif action == "music":
            context.args = data.split()
            await music_command(update, context)

        elif action == "book":
            context.args = data.split()
            await book_command(update, context)
            
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

        elif action == "decide":
            options = [opt.strip() for opt in data.split("|") if opt.strip()]
            context.args = options
            await decide_command(update, context)
            
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
            try:
                response = await ask_llm(user_text)
                if not response:
                    await status_msg.edit_text("⚠️ The AI didn't return an answer. Is the API down?")
                else:
                    clean_response = response.replace("*", "").replace("#", "")
                    await status_msg.edit_text(clean_response)
            except Exception as e:
                logger.error(f"❌ General Chat Error: {e}")
                await status_msg.edit_text(f"❌ My brain is foggy: {str(e)}")


# ==========================================
# VOICE ROUTING HANDLER
# ==========================================
async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Transcribes voice notes and routes them as multiple parallel commands."""
    if not is_authorized(update): return
    logger.info(f"🎤 Voice message received from {update.effective_chat.id}")

    status_msg = await update.message.reply_text("🗣️ <i>Listening...</i>", parse_mode=ParseMode.HTML)

    try:
        voice_file = await update.message.voice.get_file()
        audio_bytes = await voice_file.download_as_bytearray()

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

        safe_transcription = html.escape(transcription)
        await status_msg.edit_text(
            f"🗣️ <b>You said:</b> <i>\"{safe_transcription}\"</i>\n"
            f"🧠 <i>Routing commands...</i>", 
            parse_mode=ParseMode.HTML
        )

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
        - decide: args = ["option1", "option2"]
        - recipe: args = ["ingredient1 ingredient2"] 
        - grocery: args = [] (to view list) OR args = ["item"] (to add)
        - grocery_remove: args = ["item"]
        - movie: args = ["topic"]
        - music: args = ["topic"]
        - book: args = ["topic"]
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
            safe_transcription = html.escape(transcription)
            await status_msg.edit_text(
                f"🗣️ <b>You said:</b> <i>\"{safe_transcription}\"</i>\n"
                f"💬 I heard you, but I didn't detect any specific commands to run!", 
                parse_mode=ParseMode.HTML
            )

        await status_msg.delete()
        
        command_map = {
            "train": train_command,
            "weather": weather_command,
            "news": news_command,
            "portfolio": portfolio_command,
            "decide": decide_command,
            "recipe": recipe_command,
            "grocery": grocery_command,
            "grocery_remove": grocery_remove_command,
            "movie": movie_command,
            "music": music_command,
            "book": book_command,
            "stats": stats_command,
            "cat": cat_command,
            "dateidea": dateidea_command,
            "research": research_command,
            "remind": remind_command
        }

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