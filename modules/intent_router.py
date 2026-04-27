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

from commands.general import start_command
from commands.finance_news import portfolio_command, news_command
from commands.knowledge_util import research_command, weather_command, remind_command, time_command, memo_command
from commands.shared_life import grocery_command, grocery_remove_command, recipe_command, decide_command
from commands.health_fitness import train_command, stats_command
from commands.fun_extras import movie_command, music_command, book_command, cat_command, dateidea_command

logger = logging.getLogger(__name__)


# ==========================================
# Helper Functions
# ==========================================
def log_interaction(context, user_input, bot_output):
    """Saves an interaction to the sliding window memory."""
    if 'chat_history' not in context.user_data:
        context.user_data['chat_history'] = []
    
    context.user_data['chat_history'].append(f"User: {user_input}")
    context.user_data['chat_history'].append(f"MattouBot: {bot_output}")
    
    if len(context.user_data['chat_history']) > 6:
        context.user_data['chat_history'] = context.user_data['chat_history'][-6:]


def should_bot_wake_up(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """Determines if the bot should process a message in a group chat."""
    chat_type = update.effective_chat.type
    
    # 1. Always wake up in private messages
    if chat_type not in ['group', 'supergroup']:
        return True

    text_lower = text.strip().lower()

    # 2. Direct Summons (Names, Replies, Commands, Fast-paths)
    if any(name in text_lower for name in ["mattou", "@mattoubot"]): return True
    if update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id: return True
    if text_lower.startswith("/"): return True
    if text_lower in ["chat", "cat"]: return True

    # 3. Smart Implicit Commands (Checking for intent combinations)
    
    # Grocery: "ajoute/add" + "liste/courses"
    if any(w in text_lower for w in ["ajoute", "add", "enlève", "remove"]) and any(w in text_lower for w in ["liste", "courses", "list"]):
        return True
        
    # Reminders: "rappelle/remind" + a preposition
    if any(w in text_lower for w in ["rappelle", "remind"]) and any(w in text_lower for w in ["dans", "in", "à", "de", "at", "to"]):
        return True
        
    # Decisions: "choisis/décide" + "ou/entre"
    if any(w in text_lower for w in ["décide", "choisis", "decide", "choose"]) and any(w in text_lower for w in ["ou", "or", "entre", "between"]):
        return True
        
    # Single strong keywords (Weather, Fitness, Media)
    strong_keywords = ["météo", "weather", "recette", "recipe", "strava", "bilan", "stats"]
    if any(w in text_lower for w in strong_keywords):
        return True

    return False

# ==========================================
# The Natural Language Understanding Brain
# ==========================================
async def parse_intent(user_text: str, history: list = None) -> list:
    """
    Analyzes raw text to determine which bot functions to trigger.
    Returns a LIST of dictionaries with 'action' and 'data'.
    """
    history_text = "\n".join(history) if history else "None."
    
    prompt = f"""
    [ROLE]
    You are a world-class NLU (Natural Language Understanding) routing engine. 
    Your job is to decipher user intent, extract necessary parameters, and map them to strict system actions.

    [CORE RULES]
    1. TYPO TOLERANCE: Aggressively autocorrect intent in your mind.
    2. SEMANTIC MATCHING: Look for the *meaning* behind the words, not just exact keywords.
    3. MEDIA VS RESEARCH: If asking for something to watch, read, or listen to, ALWAYS route to movie, book, or music.
    4. THE "CHAT" FALLBACK: Only use the "chat" action if the message is purely conversational, a joke, or general knowledge.
    5. COMPOUND INTENTS: If the user asks to do multiple distinct things, you MUST break them down into MULTIPLE objects in the JSON array.

    [ACTION DICTIONARY & EXAMPLES]
    Format -> action_name: [Trigger description] -> Data Payload
    
    --- GENERAL & SYSTEM ---
    - start: User types "start", "help", wants to see the command list, or asks what you can do.
      * Ex: "start" -> data: "" | "what can you do?" -> data: "" | "help" -> data: ""

    --- LISTS & FOOD ---
    - grocery_add: User wants to add/buy an item. 
      * Ex: "ajoute du lait" -> data: "lait" | "need eggs and bread" -> data: "eggs and bread"
    - grocery_remove: User wants to remove/delete/cross off an item. 
      * Ex: "enlève les pommes" -> data: "pommes" | "crossed off milk" -> data: "milk"
    - grocery_list: User wants to see/read the current shopping list. 
      * Ex: "qu'est-ce qu'il manque ?" -> data: "" | "show the list" -> data: ""
    - recipe: User wants cooking ideas or recipes based on items. 
      * Ex: "que faire avec du poulet et du riz" -> data: "poulet riz" | "dinner ideas" -> data: "dinner"
    - decide: User wants to choose between options. 
      * Ex: "tacos ou pizza" -> data: "tacos | pizza" | "pick red, blue, or green" -> data: "red | blue | green"

    --- DATA & INFO ---
    - weather: User asks about temperature or forecasts. 
      * Ex: "fait-il beau à Paris" -> data: "Paris" | "weather tomorrow" -> data: ""
    - portfolio: User asks about stocks, markets, investments. 
      * Ex: "comment va ma bourse" -> data: "" | "crypto update" -> data: ""
    - news: User asks for global news, geopolitics. 
      * Ex: "quoi de neuf dans le monde" -> data: "" | "headlines" -> data: ""
    - research: User asks for CURRENT events, live data, or highly specific news. 
      * Ex: "qui a gagné le match hier" -> data: "qui a gagné le match hier" | "SpaceX launch status" -> data: "SpaceX launch status"
    - time: User asks what time it is, what day it is, or wants the current date/clock.
      * Ex: "quelle heure est il" -> data: "" | "what is the date today" -> data: ""
    - memo: User asks to make a reminder of what he says later.
      * Ex: "rappelle-moi que j'ai mangé du boeuf ce midi" -> data: "j'ai mangé du boeuf ce midi" | "note that I went shopping at 5pm" -> data: "I went shopping at 5pm"

    --- HEALTH & LIFESTYLE ---
    - train: User wants a workout or training plan. 
      * Ex: "séance de jambes" -> data: "jambes" | "5k run easy" -> data: "running easy 5k"
    - stats: User wants to see their Strava or workouts. 
      * Ex: "mes stats strava" -> data: "" | "how much did I run this week" -> data: ""
    - dateidea: User wants a romantic plan or date idea. 
      * Ex: "quoi faire ce soir à Genève" -> data: "Genève" | "romantic evening" -> data: ""

    --- UTILITIES & FUN ---
    - remind: User wants a timer or reminder. 
      * Ex: "rappel dans 10 min de sortir le four" -> data: "10m sortir le four" | "timer 5m for tea" -> data: "5m for tea"
    - cat: User wants a cat gif. 
      * Ex: "envoie un chat" -> data: "" | "need feline dopamine" -> data: ""
    - music: User wants a song or playlist recommendation. 
      * Ex: "musique pour courir" -> data: "pour courir" | "jazz vibes" -> data: "jazz"
    - movie: User wants a movie or series recommendation. 
      * Ex: "film d'horreur avec des potes" -> data: "horreur potes" | "comedy series" -> data: "comedy"
    - book: User wants a book or novel recommendation. 
      * Ex: "livre de dev perso" -> data: "développement personnel" | "sci-fi novel" -> data: "sci-fi"

    --- FALLBACK, CONVERSATION & IGNORE ---
    - ignore: The user is talking to someone else in a group chat, or the message is clearly not directed at you.
      * Ex: "tu veux manger quoi ce soir ?" -> data: "" | "j'ai acheté le lait" -> data: ""
    - chat: User EXPLICITLY asks the bot a question, wants a joke, or makes conversation WITH THE BOT. 
      * Ex: "comment soigner un hoquet" -> data: "comment soigner un hoquet" | "hello" -> data: "hello"

    [PREVIOUS CONVERSATION CONTEXT]
    {history_text}

    [USER MESSAGE]
    "{user_text}"

    [OUTPUT STRICT FORMAT]
    You must output ONLY a valid JSON array of objects. No explanations.
    [
      {{"action": "exact_action_name", "data": "extracted_string"}}
    ]
    """
    
    response = await ask_llm(prompt)
    
    if not response:
        return [{"action": "chat", "data": user_text}]
        
    try:
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            return json.loads(match.group())
        else:
            logger.warning(f"No JSON array found in LLM response. Raw: {response}")
            return [{"action": "chat", "data": user_text}]
            
    except Exception as e:
        logger.error(f"Intent Parse Error: {e} - Raw: {response}")
        return [{"action": "chat", "data": user_text}]


# ==========================================
# TEXT ROUTING HANDLER
# ==========================================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Intercepts standard text messages and routes them without needing /commands."""
    if not is_authorized(update): return
    
    raw_text = update.message.text
    if not raw_text: return

    if not should_bot_wake_up(update, context, raw_text): return
        
    user_text = raw_text.strip().lower()

    if user_text == "chat":
        context.user_data['lang'] = 'fr'
        return await cat_command(update, context)
    
    if user_text == "cat":
        context.user_data['lang'] = 'en'
        return await cat_command(update, context)

    if user_text == "/reset":
        context.user_data['chat_history'] = []
        await update.message.reply_text("🧹 <i>Memory wiped! What do you want to talk about next?</i>", parse_mode=ParseMode.HTML)
        return

    history = context.user_data.get('chat_history', [])
    intents = await parse_intent(user_text, history)

    for intent in intents:
        action = intent.get("action")
        data = intent.get("data", "")

        logger.info(f"🧠 NLU Intent Detected: {action} | Data: {data}")

        if action == "start":
            await start_command(update, context)

        elif action == "grocery_add":
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
            context.args = data.split() if data else []
            await news_command(update, context)

        elif action == "time":
            await time_command(update, context)

        elif action == "memo":
            await memo_command(update, context, nlu_data=data)
            
        elif action == "cat":
            await cat_command(update, context)
            
        elif action == "stats":
            context.args = data.split() if data else []
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
            
            if 'chat_history' not in context.user_data:
                context.user_data['chat_history'] = []
                
            history_text = "\n".join(context.user_data['chat_history']) if context.user_data['chat_history'] else "None."
            
            persona_prompt = f"""
            [ROLE]
            You are MattouBot, a highly intelligent, witty, and helpful personal assistant created by Matthieu.
            You are currently talking to a user in a Telegram chat.

            [INSTRUCTIONS]
            1. Be conversational, friendly, and concise. 
            2. If asked for a joke, make it actually funny and clever.
            3. If asked a general knowledge question, provide a clear, factual, and helpful answer.
            4. Keep formatting clean. Use emojis tastefully. No markdown headers.
            
            [PREVIOUS CONVERSATION CONTEXT]
            {history_text}
            
            [CURRENT USER MESSAGE]
            "{user_text}"
            """
            
            try:
                response = await ask_llm(persona_prompt)
                
                if not response:
                    await status_msg.edit_text("⚠️ My brain is blank right now. Try again?")
                else:
                    clean_response = response.replace("*", "").replace("#", "")
                    await status_msg.edit_text(clean_response)
                    
                    context.user_data['chat_history'].append(f"User: {user_text}")
                    context.user_data['chat_history'].append(f"MattouBot: {clean_response}")
                    
                    if len(context.user_data['chat_history']) > 4:
                        context.user_data['chat_history'] = context.user_data['chat_history'][-4:]
                        
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
            await status_msg.edit_text("⚠️ <i>My ears are clogged. Try typing!</i>", parse_mode=ParseMode.HTML)
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

        history = context.user_data.get('chat_history', [])
        history_text = "\n".join(history) if history else "None."

        prompt = f"""
        You are a strict, highly logical API router. 
        Read this transcribed voice message: "{transcription}"
        
        Map the user's intent to one OR MORE of the available commands below.
        
        CRITICAL RULES:
        1. Extract ONLY the exact parameters needed.
        2. Detect language. Set "lang" to "fr" (French) or "en" (English).
        3. Unsupported languages -> set "command" to "unsupported_language".
        
        [PREVIOUS CONVERSATION CONTEXT]
        {history_text}
        
        AVAILABLE COMMANDS & ARGUMENTS:
        - start: args = [] (to see the help menu or what the bot can do)
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
        - remind: args = ["time", "message"]
        - time: args = []
        - memo: args = ["memo details"]
        - chat: args = ["the full user message"] (USE THIS for general conversation, questions, jokes, or advice)
            
        Return ONLY a valid JSON list of dictionaries.
        
        EXAMPLE - "Quel est le temps à Lausanne et raconte une blague":
        [
          {{"command": "weather", "args": ["Lausanne"], "lang": "fr"}},
          {{"command": "chat", "args": ["raconte une blague"], "lang": "fr"}}
        ]
        """
        
        routing_response = await ask_llm(prompt, max_tokens=200)
        
        if not routing_response:
            await status_msg.edit_text("⚠️ <i>My brain generated an empty response.</i>", parse_mode=ParseMode.HTML)
            return
            
        try:
            match = re.search(r'\[.*\]', routing_response, re.DOTALL)
            if match:
                commands_to_run = json.loads(match.group())
            else:
                raise ValueError("No JSON array found in voice routing response.")
        except Exception as e:
            logger.error(f"❌ JSON Parse Error from Voice LLM: {routing_response} | Error: {e}")
            await status_msg.edit_text("⚠️ <i>I understood the words, but my brain failed to map the commands!</i>", parse_mode=ParseMode.HTML)
            return

        if not commands_to_run:
            await status_msg.edit_text(
                f"🗣️ <b>You said:</b> <i>\"{safe_transcription}\"</i>\n"
                f"💬 I heard you, but I didn't detect any specific commands to run!", 
                parse_mode=ParseMode.HTML
            )
            return

        await status_msg.delete()
        
        command_map = {
            "start": start_command,
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
            "remind": remind_command,
            "time": time_command,
            "memo": memo_command
        }

        for cmd in commands_to_run:
            cmd_name = cmd.get("command", "").replace("/", "")
            args = cmd.get("args", [])
            lang = cmd.get("lang", "en").lower()
            
            if cmd_name == "unsupported_language" or lang not in ["en", "fr"]:
                await update.message.reply_text("⚠️ <i>I only understand English and French! / Je ne comprends que l'anglais et le français !</i>", parse_mode=ParseMode.HTML)
                continue
            
            context.user_data["lang"] = lang
            
            if cmd_name == "chat":
                chat_text = args[0] if args else transcription
                chat_status = await update.message.reply_text("<i>Thinking...</i>", parse_mode=ParseMode.HTML)
                
                if 'chat_history' not in context.user_data:
                    context.user_data['chat_history'] = []
                
                persona_prompt = f"""
                [ROLE]
                You are MattouBot, a highly intelligent, witty, and helpful personal assistant created by Matthieu.
                You are currently talking to a user via voice-to-text in Telegram.

                [INSTRUCTIONS]
                1. Be conversational, friendly, and concise. 
                2. If asked for a joke, make it actually funny and clever.
                3. If asked a general knowledge question, provide a clear, factual answer.
                4. Keep formatting clean. Use emojis tastefully. No markdown headers.
                
                [PREVIOUS CONVERSATION CONTEXT]
                {history_text}
                
                [CURRENT USER MESSAGE]
                "{chat_text}"
                """
                
                try:
                    chat_response = await ask_llm(persona_prompt)
                    if chat_response:
                        clean_response = chat_response.replace("*", "").replace("#", "")
                        await chat_status.edit_text(clean_response)
                        
                        context.user_data['chat_history'].append(f"User (Voice): {chat_text}")
                        context.user_data['chat_history'].append(f"MattouBot: {clean_response}")
                        
                        if len(context.user_data['chat_history']) > 4:
                            context.user_data['chat_history'] = context.user_data['chat_history'][-4:]
                    else:
                        await chat_status.edit_text("⚠️ My brain is blank right now.")
                except Exception as e:
                    logger.error(f"❌ Voice Chat Error: {e}")
                    await chat_status.edit_text(f"❌ My brain is foggy: {str(e)}")
            
            elif cmd_name in command_map:
                context.args = args 
                await command_map[cmd_name](update, context)
            else:
                await update.message.reply_text(f"⚠️ <i>Command '{cmd_name}' recognized by AI but not programmed yet.</i>", parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"❌ Voice Handler Error: {e}")
        await status_msg.edit_text("⚠️ <i>An error occurred while processing your voice.</i>", parse_mode=ParseMode.HTML)