import re
import html
import time
import random
import difflib
import asyncio
import logging
import datetime
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from bson.objectid import ObjectId
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

# Import everything we need from our other modules!
from modules.config import AUTHORIZED_USERS, PORTFOLIO_MAP, grocery_collection
from modules.ai_core import ask_llm
from modules.strava_api import get_strava_access_token, get_recent_strava_activities

logger = logging.getLogger(__name__)

# ==========================================
# UTILITY FUNCTIONS
# ==========================================
def is_authorized(update: Update) -> bool:
    """Checks if the user is in the authorized VIP list."""
    chat_id = update.effective_chat.id
    if chat_id in AUTHORIZED_USERS:
        return True
    logger.warning(f"🛑 UNAUTHORIZED ACCESS ATTEMPT from ID: {chat_id}")
    return False

def get_lang_rule(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Injects a strict language rule based on the user's latest voice command."""
    pref = context.user_data.get('lang', 'en')
    lang_str = "French" if pref == "fr" else "English"
    return (
        f"\n\nCRITICAL LANGUAGE RULE:\n"
        f"- You MUST write your ENTIRE response in {lang_str}.\n"
        f"- ABSOLUTE BAN: If the user's prompt is in Spanish, German, Italian, or ANY language other than English or French, you MUST NOT fulfill the request. "
        f"You must ABORT the task and reply EXACTLY and ONLY with the phrase: '⚠️ I only speak English and French!'"
    )

def parse_time_string(time_str: str) -> int:
    """Parses strings like '10', '1.5h', '90m', '45s' into total seconds."""
    time_str = time_str.lower().strip()
    
    if time_str.replace('.', '', 1).isdigit():
        return int(float(time_str) * 60)
        
    if re.match(r'^\d+(\.\d+)?h\d+$', time_str):
        time_str += 'm'
        
    total_seconds = 0
    matches = re.findall(r'([\d\.]+)([hms])', time_str)
    
    if not matches:
        raise ValueError("Could not parse time format.")
        
    for amount, unit in matches:
        val = float(amount)
        if unit == 'h': total_seconds += val * 3600
        elif unit == 'm': total_seconds += val * 60
        elif unit == 's': total_seconds += val
        
    return int(total_seconds)


# ==========================================
# GENERAL & HELP COMMANDS
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /start")
    
    welcome = (
        "<b>Hello! I am MattouBot, meow.</b> 🐾\n\n"
        "Here is what I can do for you:\n\n"
        "<b>📈 Finance & News</b>\n"
        "• /portfolio - Live market status\n"
        "• /news - Global & European geopolitics\n\n"
        "<b>🧠 Knowledge & Utility</b>\n"
        "• /research [topic] - AI deep dive\n"
        "• /weather [city] - Current conditions\n"
        "• /remind [min] [text] - Set a timer\n\n"
        "<b>🛒 Shared Life</b>\n"
        "• /grocery [item] - Add an item to the list\n"
        "• /grocery - View the current list\n"
        "• /grocery_remove [item] - Remove an item from the list\n"
        "• /grocery_empty - Clear the list\n"
        "• /decide [A], [B] - Settle an argument\n"
        "• /recipe [ingredients] - Empty fridge chef\n\n"
        "<b>💪 Health & Fitness</b>\n"
        "• /train [sport] [specs] - AI tailored workout\n"
        "• /stats - Weekly performance review\n\n"
        "<b>🎉 Fun & Extras</b>\n"
        "• /cat - Instant feline dopamine\n"
        "• /dateidea [city] - Generate a date idea\n"
        "• /movie [topic] - Recommend a movie\n"
        "• /music [topic] - Recommend a song/album/playlist\n"
        "• /book [topic] - Recommend a book/novel"
    )
    await update.message.reply_text(welcome, parse_mode=ParseMode.HTML)

# ==========================================
# FINANCE & NEWS COMMANDS
# ==========================================
async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /portfolio")
    
    status_msg = await update.message.reply_text("📈 <i>Fetching live market data...</i>", parse_mode=ParseMode.HTML)
    stats = []
    
    for ticker, name in PORTFOLIO_MAP.items():
        try:
            safe_name = html.escape(name)
            stock = yf.Ticker(ticker)
            data = await asyncio.to_thread(stock.history, period="5d")
            
            if not data.empty and len(data) >= 2:
                current = data['Close'].iloc[-1]
                prev = data['Close'].iloc[-2]
                pct = ((current - prev) / prev) * 100
                
                indicator = "🟢" if pct >= 0 else "🔴"
                stats.append(f"• <b>{safe_name}</b>:\n  <code>{indicator} {current:.2f} ({pct:+.2f}%)</code>")
            else:
                stats.append(f"• <b>{safe_name}</b>:\n  <code>⚠️ Market closed</code>")
        except Exception as e:
            logger.error(f"❌ Portfolio Error for {ticker}: {e}")
            stats.append(f"• <b>{html.escape(name)}</b>:\n  <code>⚠️ Fetch failed</code>")
    
    header = "📊 <b>Live Market Portfolio</b>\n━━━━━━━━━━━━━━━━━━━\n"
    body = "\n".join(stats)
    await status_msg.edit_text(f"{header}{body}", parse_mode=ParseMode.HTML)

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /news")
    
    status_msg = await update.message.reply_text("<i>Analyzing global headlines...</i> ⏳", parse_mode=ParseMode.HTML)
    raw_news = []
    queries = ["geopolitics world", "geopolitics Switzerland", "geopolitics France"]
    
    try:
        for q in queries:
            url = f"https://news.google.com/rss/search?q={q}+when:1d&hl=en-US&gl=US&ceid=US:en"
            res = await asyncio.to_thread(requests.get, url, timeout=10)
            soup = BeautifulSoup(res.content, "xml")
            for item in soup.find_all("item", limit=2):
                raw_news.append(item.title.text)
        
        news_context = "\n".join(raw_news)
        prompt = f"""
        [ROLE]
        You are a highly analytical Geopolitical Briefing Officer. Your task is to provide a high-level executive summary of current events for a VIP client.

        [CONTEXT]
        Raw headlines from international, Swiss, and French sources (Last 24h):
        {news_context}

        [TASK]
        Synthesize the headlines into a single, natural, and cohesive paragraph connecting the dots between events.

        [STRICT INSTRUCTIONS]
        1. OBJECTIVITY: Maintain a neutral, journalistic tone. No personal opinions.
        2. NO HALLUCINATION: If headlines are missing for a region, focus only on the data available.
        3. PLAIN TEXT ONLY: Absolutely NO HTML tags (no <b>, <i>, etc.).
        4. NO MARKDOWN: Strictly avoid all asterisks (*) and hashtags (#). Use ALL CAPS for emphasis if absolutely necessary.
        5. LANGUAGE: Adhere strictly to the language preference requested.
        6. EMOJIS: Include exactly 2 relevant emojis at the end of the text.

        [OUTPUT STRUCTURE]
        A single paragraph of 4-6 sentences. Start directly with the briefing—no introductory pleasantries.
        """
        
        prompt += get_lang_rule(context)
        summary = await ask_llm(prompt)
        safe_summary = html.escape(summary.replace('*', ''))
        await status_msg.edit_text(f"📰 <b>Geopolitical Briefing</b>\n\n{safe_summary}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ News Error: {e}")
        await status_msg.edit_text(f"⚠️ News summary failed: {str(e)}")


# ==========================================
# KNOWLEDGE & UTILITY COMMANDS
# ==========================================
async def research_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /research")
    
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("⚠️ <b>Please provide a topic!</b>\n<i>Example: /research Swiss neutrality 2026</i>", parse_mode=ParseMode.HTML)
        return

    status_msg = await update.message.reply_text(f"🔍 <i>Researching '{html.escape(query)}'...</i>", parse_mode=ParseMode.HTML)

    try:
        search_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        res = await asyncio.to_thread(requests.get, search_url, timeout=10)
        soup = BeautifulSoup(res.content, "xml")
        headlines = [item.title.text for item in soup.find_all("item", limit=5)]
        
        if headlines:
            headlines_text = "\n".join(headlines)
            prompt = f"""
            [ROLE]
            You are a senior Intelligence Analyst specializing in OSINT. Your standard is absolute factual accuracy.

            [SOURCE MATERIAL]
            Topic: {query}
            Headlines:
            {headlines_text}
            
            [TASK]
            Provide a 3-sentence situation report on '{query}' based EXCLUSIVELY on the headlines.

            [STRICT INSTRUCTIONS]
            1. STRICT SOURCE ADHERENCE: Do NOT use internal training data to add facts not found in the headlines.
            2. RELEVANCE CHECK: If the headlines lack specific information on '{query}', reply EXACTLY with: 
               "⚠️ The recent news headlines do not contain enough relevant information to provide a reliable summary."
            3. PLAIN TEXT ONLY: Absolutely NO HTML tags.
            4. NO MARKDOWN: Absolutely NO asterisks (*) or hashtags (#).

            [OUTPUT STRUCTURE]
            Exactly three sentences. No preamble.
            """
        else:
            prompt = f"""
            [ROLE]
            You are a highly accurate Research Librarian.

            [TASK]
            Explain the core concept or historical facts of '{query}'.

            [STRICT INSTRUCTIONS]
            1. FACTUAL GROUNDING: Rely only on verified, objective information.
            2. UNCERTAINTY PROTOCOL: If you do not have definitive knowledge, reply EXACTLY with:
               "⚠️ I do not have enough verified, reliable information to summarize this topic accurately."
            3. PLAIN TEXT ONLY: Absolutely NO HTML tags.
            4. NO MARKDOWN: Absolutely NO asterisks (*) or hashtags (#).

            [OUTPUT STRUCTURE]
            A concise 3-sentence summary. No preamble.
            """
            
        prompt += get_lang_rule(context)
        analysis = await ask_llm(prompt)
        safe_analysis = html.escape(analysis.replace('*', ''))
        safe_query = html.escape(query)
        await status_msg.edit_text(f"📝 <b>Research Summary: {safe_query}</b>\n\n{safe_analysis}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Research error: {e}")
        await status_msg.edit_text(f"⚠️ Research failed: {str(e)}")

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /weather")
    
    city_query = " ".join(context.args) or "Lausanne"
    display_name = html.escape(city_query.title())
    
    status_msg = await update.message.reply_text(f"<i>Looking up the weather for {display_name}...</i> 🌍", parse_mode=ParseMode.HTML)
    
    weather_url = f"https://wttr.in/{city_query}?format=j1"
    headers = {"User-Agent": "MattouBot/1.0 (Telegram Assistant)"}
    
    try:
        res = await asyncio.to_thread(requests.get, weather_url, headers=headers, timeout=10)
        
        if res.status_code != 200:
            await status_msg.edit_text(f"⚠️ <i>I couldn't find weather data for '<b>{display_name}</b>'. Did you make a typo?</i>", parse_mode=ParseMode.HTML)
            return
            
        data = res.json()
        current = data['current_condition'][0]
        temp = current['temp_C']
        condition = current['weatherDesc'][0]['value'] # wttr.in gives us the text description directly!
        
        prompt = f"""
        [ROLE]
        You are a witty, slightly sassy, and caring virtual assistant managing a couple's daily life. 

        [CONTEXT]
        Location: {display_name}
        Current Temperature: {temp}°C
        Sky Conditions: {condition}

        [TASK]
        Write a short, high-personality weather report. Tell them how it feels and give a specific outfit/activity recommendation.

        [STRICT INSTRUCTIONS]
        1. STRUCTURE: Exactly 2 sentences. No intros, no "Sure!", just start.
        2. TONE: Cute, sassy, and practical.
        3. DATA-DRIVEN: 
        - If < 10°C: Recommend layers/warmth.
        - If > 25°C: Recommend hydration/light clothes.
        - If rain/clouds: Recommend umbrella/coziness.
        4. PLAIN TEXT ONLY: Absolutely NO HTML tags (no <b>, no <i>, no <br>).
        5. NO MARKDOWN: Absolutely NO asterisks (*) or hashtags (#). 
        6. EMOJIS: Include exactly 2 emojis. No more, no less.

        [OUTPUT EXAMPLE]
        It is currently 18°C with clear skies in Lausanne. Put on that leather jacket you look so good in and grab a coffee before you freeze your toes off. ☕️🧥
        """

        prompt += get_lang_rule(context)
        forecast = await ask_llm(prompt, max_tokens=200)
        safe_forecast = html.escape(forecast.replace('*', ''))
        await status_msg.edit_text(f"🌍 <b>Forecast for {display_name}</b>\n\n{safe_forecast}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Weather Command Error: {e}")
        await status_msg.edit_text(f"⚠️ Weather data unavailable: {str(e)}")

async def remind_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    safe_message = html.escape(job.data)
    await context.bot.send_message(
        chat_id=job.chat_id, 
        text=f"🔔 <b>REMINDER:</b> {safe_message}", 
        parse_mode=ParseMode.HTML
    )

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /remind")
    chat_id = update.effective_chat.id
    
    try:
        time_input = context.args[0]
        message = " ".join(context.args[1:])
        total_seconds = parse_time_string(time_input)
        
        if total_seconds <= 0:
            await update.message.reply_text("⚠️ <i>Time must be greater than 0.</i>", parse_mode=ParseMode.HTML)
            return
        if not message:
            await update.message.reply_text("⚠️ <i>What do you want me to remind you about?</i>", parse_mode=ParseMode.HTML)
            return
            
        context.job_queue.run_once(remind_callback, total_seconds, data=message, chat_id=chat_id)
        
        if total_seconds < 60:
            time_display = f"{total_seconds} second(s)"
        else:
            mins = total_seconds // 60
            hrs = mins // 60
            leftover_mins = mins % 60
            if hrs > 0:
                time_display = f"{hrs} hour(s)" + (f" and {leftover_mins} minute(s)" if leftover_mins else "")
            else:
                time_display = f"{mins} minute(s)"
        
        safe_message = html.escape(message)
        await update.message.reply_text(f"🕒 Got it! I will remind you to <b>{safe_message}</b> in {time_display}.", parse_mode=ParseMode.HTML)
    except (IndexError, ValueError) as e:
        error_msg = (
            "⚠️ <b>Usage:</b> /remind [time] [message]\n\n"
            "<i>Examples:</i>\n"
            "• <code>/remind 10 flip laundry</code> (10 mins)\n"
            "• <code>/remind 1h30 check the oven</code>\n"
            "• <code>/remind 45s take a breath</code>"
        )
        await update.message.reply_text(error_msg, parse_mode=ParseMode.HTML)


# ==========================================
# SHARED LIFE COMMANDS
# ==========================================
def build_grocery_ui():
    """Helper function to fetch the DB and build the interactive inline keyboard."""
    try:
        items_cursor = grocery_collection.find()
        docs = list(items_cursor)
        
        if not docs:
            return "🛒 <b>The grocery list is currently empty!</b>", None
            
        text = f"🛒 <b>Shared Shopping List ({len(docs)} items):</b>\n<i>Tap an item to cross it off.</i>"
        
        keyboard = []
        for doc in docs:
            item_name = doc['item']
            item_id = str(doc['_id'])
            safe_item = html.escape(item_name)
            keyboard.append([InlineKeyboardButton(f"{safe_item}", callback_data=f"g_rm_{item_id}")])
            
        keyboard.append([InlineKeyboardButton("🧹 Empty Entire List", callback_data="g_empty")])
        
        return text, InlineKeyboardMarkup(keyboard)
    except Exception as e:
        logger.error(f"❌ Grocery UI Build Error: {e}")
        return "⚠️ <i>Database error.</i>", None

async def grocery_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /grocery")
    item = " ".join(context.args)
    
    if not item:
        text, reply_markup = build_grocery_ui()
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return

    try:
        grocery_collection.insert_one({"item": item})
        text, reply_markup = build_grocery_ui()
        safe_item = html.escape(item)
        await update.message.reply_text(f"✅ Added <b>{safe_item}</b>!\n\n{text}", reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Grocery Add Error: {e}")
        await update.message.reply_text("⚠️ <i>Failed to add the item. The cart is stuck!</i>", parse_mode=ParseMode.HTML)

async def grocery_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Listens for the user tapping the inline buttons."""
    if not is_authorized(update): return
    
    query = update.callback_query
    await query.answer() 
    
    data = query.data
    
    try:
        if data.startswith("g_rm_"):
            item_id = data.replace("g_rm_", "")
            grocery_collection.delete_one({"_id": ObjectId(item_id)})
            
        elif data == "g_empty":
            grocery_collection.delete_many({})
            
        text, reply_markup = build_grocery_ui()
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)  
      
    except Exception as e:
        logger.error(f"❌ Grocery Callback Error: {e}")
        pass

async def grocery_remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    item_to_remove = " ".join(context.args).strip()
    if not item_to_remove: return
    try:
        docs = list(grocery_collection.find())
        current_items = [doc["item"] for doc in docs]
        matches = [i for i in current_items if item_to_remove.lower() in i.lower()]
        best_match = matches[0] if matches else (difflib.get_close_matches(item_to_remove, current_items, n=1, cutoff=0.3) or [None])[0]
        
        if best_match:
            grocery_collection.delete_one({"item": best_match})
            await update.message.reply_text(f"✅ Removed <b>{html.escape(best_match)}</b>!", parse_mode=ParseMode.HTML)
    except Exception: pass

async def grocery_empty_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    grocery_collection.delete_many({})
    await update.message.reply_text("🧹 <b>Grocery list cleared!</b>", parse_mode=ParseMode.HTML)

async def decide_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /decide")
    options_string = " ".join(context.args)
    
    if not options_string:
        await update.message.reply_text("⚠️ <b>Usage:</b> /decide [option 1], [option 2]\n<i>Example: /decide Pizza, Sushi</i>", parse_mode=ParseMode.HTML)
        return
        
    options = [opt.strip() for opt in options_string.split(",")]
    if len(options) < 2:
        await update.message.reply_text("⚠️ <i>I need at least TWO options to make a decision! Separate them with commas.</i>", parse_mode=ParseMode.HTML)
        return
        
    choice = random.choice(options)
    
    status_msg = await update.message.reply_text("⚖️ <i>Weighing the options...</i>", parse_mode=ParseMode.HTML)
    await asyncio.sleep(1)
    await status_msg.edit_text("🎲 <i>Running the algorithms...</i>", parse_mode=ParseMode.HTML)
    await asyncio.sleep(1.2)
    
    safe_choice = html.escape(choice)
    await status_msg.edit_text(f"🎯 <b>Decision Made:</b>\n\nI have spoken. You are going with: <b>{safe_choice}</b>", parse_mode=ParseMode.HTML)

async def recipe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    query = update.callback_query
    if query:
        await query.answer()
        logger.info(f"▶️ User {update.effective_chat.id} triggered re-roll for /recipe")
        ingredients = context.user_data.get('last_recipe', '')
    else:
        logger.info(f"▶️ User {update.effective_chat.id} triggered /recipe")
        ingredients = " ".join(context.args)
        context.user_data['last_recipe'] = ingredients
        
    if not ingredients:
        await update.effective_message.reply_text("⚠️ <b>Usage:</b> /recipe [ingredient 1], [ingredient 2]", parse_mode=ParseMode.HTML)
        return
        
    status_msg = await update.effective_message.reply_text("👨‍🍳 <i>Putting on my chef's hat and reviewing your ingredients...</i>", parse_mode=ParseMode.HTML)
    
    prompt = f"""
    [ROLE]
    You are an inventive Michelin-star chef who specializes in "fridge-clearing" gourmet cooking.

    [CONTEXT]
    Available ingredients: {ingredients}
    
    [TASK]
    Invent a creative, delicious, and easy-to-make dinner recipe using these ingredients.

    [STRICT INSTRUCTIONS]
    1. INGREDIENT STRICTNESS: Prioritize listed ingredients. Assume a basic pantry (oil, salt, pepper, water), but no other major items.
    2. TONE: Encouraging, professional, and slightly romantic.
    3. PLAIN TEXT ONLY: Absolutely NO HTML tags.
    4. NO MARKDOWN: Strictly avoid all Markdown (no asterisks *, no hashtags #). 
    5. FORMATTING: Use ALL CAPS for section titles. Use standard text bullet points (•) for ingredients and numbers (1., 2.) for steps.

    [OUTPUT STRUCTURE]
    [CATCHY RECIPE TITLE IN ALL CAPS]

    🛒 INGREDIENTS:
    • [Item 1]
    • [Item 2]

    👨‍🍳 INSTRUCTIONS:
    1. [Step 1]
    2. [Step 2]
    """
    prompt += get_lang_rule(context)
    recipe_output = await ask_llm(prompt)
    
    keyboard = [[InlineKeyboardButton("🔄 Re-roll", callback_data="reroll_recipe")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await status_msg.edit_text(f"👨‍🍳 RECIPE FOUND:\n\n{recipe_output}", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"❌ Recipe Display Error: {e}")
        await status_msg.edit_text(f"Recipe output:\n\n{recipe_output}", reply_markup=reply_markup)


# ==========================================
# HEALTH & FITNESS COMMANDS
# ==========================================
async def train_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /train")
    
    request_details = " ".join(context.args)
    if not request_details:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> /train [Sport] [Specifications]\n"
            "<i>Examples:</i>\n"
            "• /train running easy 5k\n"
            "• /train gym push day hypertrophy\n"
            "• /train swimming sprint intervals", 
            parse_mode=ParseMode.HTML
        )
        return
        
    status_msg = await update.message.reply_text("🏃‍♂️ <i>Syncing with Strava and designing your workout...</i>", parse_mode=ParseMode.HTML)
    history_text = await get_recent_strava_activities(limit=5)
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")
    
    prompt = f"""
    [ROLE]
    You are an elite, highly knowledgeable personal trainer and sports scientist.

    [CONTEXT]
    - Today's Date: {current_date}
    - Client Request: {request_details}
    - Recent Strava History:
    {history_text}
    
    [TASK]
    Design a tailored, one-off workout session based on the goal and current fatigue levels.

    [STRICT INSTRUCTIONS]
    1. FATIGUE ANALYSIS: Distinguish between sports. If history says 'Run', legs may be tired but swimming is fresh.
    2. DATA ACCURACY: Do not hallucinate distances. 
    3. PACE INTELLIGENCE: 
       - RUNNING: Calculate baseline pace (min/km). Prescribe a target pace in min/km.
       - SWIMMING: Prescribe pace in min/100m.
    4. PLAIN TEXT ONLY: Absolutely NO HTML tags.
    5. NO MARKDOWN: Absolutely NO asterisks (*) or hashtags (#). Use ALL CAPS for headers.
    6. EMOJIS: Use exactly 3 emojis total, integrated naturally. 

    [OUTPUT STRUCTURE]
    📊 RECENT TRAINING HISTORY
    • [DD/MM]: [Sport] - [Distance]km - [Duration] mins (Only show distance if > 0)

    🎯 [CATCHY WORKOUT TITLE IN ALL CAPS]

    🔥 WARM-UP
    • [Drill/distance]

    ⚡ MAIN SET
    • [Core workout]

    🧘 COOL-DOWN
    • [Recovery action]
    """
    
    prompt += get_lang_rule(context)
    workout = await ask_llm(prompt)
    try:
        await status_msg.edit_text(f"🏃‍♂️ WORKOUT PLAN:\n\n{workout}")
    except Exception as e:
        logger.error(f"❌ Train Display Error: {e}")
        await status_msg.edit_text(workout)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /stats")
    
    status_msg = await update.message.reply_text("📊 <i>Crunching your weekly numbers...</i>", parse_mode=ParseMode.HTML)
    
    access_token = await get_strava_access_token()
    if not access_token:
        await status_msg.edit_text("⚠️ <i>Could not connect to Strava to fetch stats.</i>", parse_mode=ParseMode.HTML)
        return

    # Calculate the exact timestamp for 7 days ago
    seven_days_ago = int(time.time()) - (7 * 24 * 3600)
    
    url = f"https://www.strava.com/api/v3/athlete/activities?after={seven_days_ago}&per_page=30"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        res = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
        activities = res.json()
        
        if not activities:
            await status_msg.edit_text("📊 <b>Weekly Stats</b>\n\nYou haven't logged any activities in the last 7 days. Time to get moving! 🏃‍♂️💨", parse_mode=ParseMode.HTML)
            return
        
        logger.info(f"🚀 Triggering background PostgreSQL sync for {len(activities)} weekly activities...")
        from modules.strava_api import sync_activities_to_db
        await sync_activities_to_db(activities)
            
        total_time = 0
        total_load = 0
        activity_count = len(activities)
        sport_stats = {}
        
        for act in activities:
            sport = act.get('sport_type', 'Activity')
            dist_km = act.get('distance', 0) / 1000
            time_min = act.get('moving_time', 0) / 60
            
            desc = act.get('description', '') or ''
            act_load = 0
            if "charge d'entraînement" in desc:
                match = re.search(r'(\d+)\s*charge', desc)
                if match: act_load = int(match.group(1))

            total_time += time_min
            total_load += act_load
            
            if sport not in sport_stats:
                sport_stats[sport] = {'count': 0, 'distance': 0, 'time': 0, 'load': 0}
                
            sport_stats[sport]['count'] += 1
            sport_stats[sport]['distance'] += dist_km
            sport_stats[sport]['time'] += time_min
            sport_stats[sport]['load'] += act_load

        hrs = int(total_time // 60)
        mins = int(total_time % 60)
        
        stats_lines = [
            f"<b>Total Workouts:</b> {activity_count}",
            f"<b>Total Active Time:</b> {hrs}h {mins}m"
        ]
        if total_load > 0:
            stats_lines.append(f"<b>Total Coros Load:</b> {total_load}")
            
        stats_lines.append("\n<b>🏅 Breakdown by Sport:</b>")
        
        for sport, data in sport_stats.items():
            s_hrs = int(data['time'] // 60)
            s_mins = int(data['time'] % 60)
            time_str = f"{s_hrs}h {s_mins}m" if s_hrs > 0 else f"{s_mins}m"
            
            line = f"• <b>{sport}:</b> {data['count']} session(s) | {time_str}"
            if data['distance'] > 0:
                line += f" | {data['distance']:.1f} km"
            if data['load'] > 0:
                line += f" | Load: {data['load']}"
            stats_lines.append(line)
            
        stats_text = "\n".join(stats_lines)
        
        prompt = f"""
        [ROLE]
        You are an elite personal trainer. 

        [CONTEXT]
        Client's training from the last 7 days:
        {stats_text}
        
        [TASK]
        Write a short, 2-sentence encouraging weekly performance review based on their mix of sports.

        [STRICT INSTRUCTIONS]
        1. SMART GYM LOGIC: If they did gym/weight training with 0 Coros Load, DO NOT say they were resting. Acknowledge the strength work!
        2. RECOVERY PROTOCOL: If Total Coros Load > 400, strictly advise them to prioritize recovery.
        3. PLAIN TEXT ONLY: Absolutely NO HTML tags.
        4. NO MARKDOWN: Absolutely NO asterisks (*) or hashtags (#).
        5. EMOJIS: Maximum 2 emojis.

        [OUTPUT STRUCTURE]
        A clean, 2-sentence review. No introductions, just start speaking.
        """
        
        prompt += get_lang_rule(context)
        ai_review = await ask_llm(prompt)
        safe_review = html.escape(ai_review)
        final_message = f"📊 <b>7-Day Performance Review</b>\n\n{stats_text}\n\n<b>Coach's Note:</b>\n{safe_review}"
        await status_msg.edit_text(final_message, parse_mode=ParseMode.HTML)
        
    except Exception as e:
            logger.error(f"❌ Stats Logic/Display Error: {e}")
            await status_msg.edit_text(f"⚠️ Stats summary failed: {str(e)}")


# ==========================================
# FUN & EXTRAS COMMANDS
# ==========================================
async def dateidea_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    query = update.callback_query
    if query:
        await query.answer()
        logger.info(f"▶️ User {update.effective_chat.id} triggered re-roll for /dateidea")
        location_query = context.user_data.get('last_dateidea', 'the Vaud/Valais region of Switzerland')
    else:
        logger.info(f"▶️ User {update.effective_chat.id} triggered /dateidea")
        location_query = " ".join(context.args) or "the Vaud/Valais region of Switzerland"
        context.user_data['last_dateidea'] = location_query
        
    display_location = location_query.title()
    safe_display = html.escape(location_query.title())
    status_msg = await update.effective_message.reply_text(f"<i>Thinking of something romantic in {safe_display}...</i> 🍷", parse_mode=ParseMode.HTML)
    current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")
    
    weather_condition = "Unknown"
    temp = "Unknown"
    
    try:
        url = f"https://wttr.in/{location_query}?format=j1"
        headers = {"User-Agent": "MattouBot/1.0 (Telegram Assistant)"}
        res = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            temp = data['current_condition'][0]['temp_C']
            weather_condition = data['current_condition'][0]['weatherDesc'][0]['value'].lower()
    except Exception as e:
        logger.error(f"Weather fetch failed for dateidea: {e}")

    vibes = ["cozy and relaxed", "adventurous outdoors", "cultural and artistic", "foodie focused", "budget-friendly"]
    vibe = random.choice(vibes)
    
    prompt = f"""
    [ROLE]
    You are a creative, thoughtful Romantic Concierge with deep expertise in local events.

    [CONTEXT]
    - Location: {display_location}
    - Today's Date: {current_date}
    - Current Weather: {temp}°C, {weather_condition}
    - Requested Vibe: {vibe}
    
    [TASK]
    Suggest one unique, specific, and fun date idea tailored perfectly to the context.

    [STRICT INSTRUCTIONS]
    1. WEATHER GROUNDING: If raining/cold, the date must be indoors. If sunny, prioritize outdoors.
    2. SEASONAL AWARENESS: Ensure the activity is possible on {current_date}. 
    3. LOCAL LOGIC: The activity must be geographically relevant to {display_location}. No generic parks.
    4. PLAIN TEXT ONLY: Absolutely NO HTML tags.
    5. NO MARKDOWN: Absolutely NO asterisks (*) or hashtags (#). Use ALL CAPS for the title.
    6. EMOJIS: Use exactly 2 or 3 emojis total.

    [OUTPUT STRUCTURE]
    [CATCHY TITLE IN ALL CAPS] - Cost: [Free/$/$$/$$$]
    [A 2-sentence engaging description explaining the activity and why it fits the {weather_condition} weather.]
    """
    
    prompt += get_lang_rule(context)
    idea = await ask_llm(prompt) 
    
    keyboard = [[InlineKeyboardButton("🔄 Re-roll", callback_data="reroll_dateidea")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await status_msg.edit_text(f"✨ {idea}", reply_markup=reply_markup)


async def cat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    query = update.callback_query
    if query:
        await query.answer()
        logger.info(f"▶️ User {update.effective_chat.id} triggered re-roll for /cat")
    else:
        logger.info(f"▶️ User {update.effective_chat.id} triggered /cat")
        
    try:
        cat_url = f"https://api.thecatapi.com/v1/images/search?mime_types=gif"
        res = await asyncio.to_thread(requests.get, cat_url, timeout=10)
        data = res.json()
        
        keyboard = [[InlineKeyboardButton("🔄 Another cat!", callback_data="reroll_cat")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if query:
            try:
                await update.effective_message.delete()
            except Exception:
                pass
                
        await update.effective_message.reply_animation(data[0]['url'], reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"❌ Cat API error: {e}")
        await update.effective_message.reply_text("The cats are sleeping. 😴")

async def movie_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    query = update.callback_query
    if query:
        await query.answer()
        logger.info(f"▶️ User {update.effective_chat.id} triggered re-roll for /movie")
        keywords = context.user_data.get('last_movie', 'a great movie')
    else:
        logger.info(f"▶️ User {update.effective_chat.id} triggered /movie")
        keywords = " ".join(context.args)
        context.user_data['last_movie'] = keywords
        
    if not keywords:
        usage_text = (
            "⚠️ <b>Usage:</b> /movie [vibe/genre/actors]\n"
            "<i>Examples:</i>\n"
            "• <code>/movie scary with dogs but a happy ending</code>\n"
            "• <code>/movie film d'animation avec un chat</code>\n"
            "• <code>/movie mind-bending sci-fi</code>"
        )
        await update.effective_message.reply_text(usage_text, parse_mode=ParseMode.HTML)
        return

    safe_keywords = html.escape(keywords)
    status_msg = await update.effective_message.reply_text(f"🍿 <i>Dimming the lights and searching for '{safe_keywords}'...</i>", parse_mode=ParseMode.HTML)
    
    prompt = f"""
    [ROLE]
    You are an elite, opinionated Film Sommelier. 

    [CONTEXT]
    The user wants a movie recommendation based on these vibes: "{keywords}"
    
    [TASK]
    Suggest ONE perfect movie. 

    [STRICT INSTRUCTIONS]
    1. MOVIES ONLY: Suggest a feature film, a TV series or show.
    2. QUALITY: Pick a genuinely good movie (IMDb 7.0+). No generic garbage unless requested.
    3. THE PITCH: Write exactly 1 or 2 sentences that explain the plot AND why it fits their keywords.
    4. PLAIN TEXT ONLY: Absolutely NO HTML tags.
    5. NO MARKDOWN: Absolutely NO asterisks (*) or hashtags (#). 
    6. LANGUAGE SYNC: You MUST reply entirely in the language the user used (e.g., if French, the whole response must be in French).

    [OUTPUT STRUCTURE]
    [Movie Title] ([Year])
    [Translated word for "Genre"]: [Genre]
    
    [Translated word for "Pitch"]: [Your 1-2 sentence pitch]
    """
    
    prompt += get_lang_rule(context)
    suggestion = await ask_llm(prompt) 
    
    keyboard = [[InlineKeyboardButton("🔄 Re-roll", callback_data="reroll_movie")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await status_msg.edit_text(suggestion, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"❌ Movie Display Error: {e}")
        await status_msg.edit_text(f"⚠️ Movie suggestion failed: {str(e)}")

async def music_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    query = update.callback_query
    if query:
        await query.answer()
        logger.info(f"▶️ User {update.effective_chat.id} triggered re-roll for /music")
        keywords = context.user_data.get('last_music', 'chill acoustic')
    else:
        logger.info(f"▶️ User {update.effective_chat.id} triggered /music")
        keywords = " ".join(context.args)
        context.user_data['last_music'] = keywords
        
    if not keywords:
        usage_text = (
            "⚠️ <b>Usage:</b> /music [genre/vibe/activity]\n"
            "<i>Examples:</i>\n"
            "• <code>/music alternative rock</code>\n"
            "• <code>/music playlist de musculation</code>\n"
            "• <code>/music cooking pasta with wine</code>"
        )
        await update.effective_message.reply_text(usage_text, parse_mode=ParseMode.HTML)
        return

    safe_keywords = html.escape(keywords)
    status_msg = await update.effective_message.reply_text(
        f"🎧 <i>Putting on my headphones and crate-digging for '{safe_keywords}'...</i>", 
        parse_mode=ParseMode.HTML
    )
    
    prompt = f"""
    [ROLE]
    You are an elite, highly opinionated DJ and Music Curator. 

    [CONTEXT]
    The user wants a music recommendation based on these vibes: "{keywords}"
    
    [TASK]
    Suggest ONE perfect song, album, or specific playlist concept.

    [STRICT INSTRUCTIONS]
    1. QUALITY: Pick something genuinely great. Avoid the most obvious top-40 clichés.
    2. THE PITCH: Write exactly 1 or 2 sentences explaining why this track/album fits their vibe.
    3. PLAIN TEXT ONLY: Absolutely NO HTML tags.
    4. NO MARKDOWN: Absolutely NO asterisks (*) or hashtags (#). 
    5. LANGUAGE SYNC: You MUST reply entirely in the language the user used (e.g., if French, the whole response must be in French).

    [OUTPUT STRUCTURE]
    [Song/Album Title] by [Artist]
    [Translated word for "Genre"]: [Genre]
    
    [Translated word for "Pitch"]: [Your 1-2 sentence pitch]
    """
    
    prompt += get_lang_rule(context)
    suggestion = await ask_llm(prompt) 
    
    keyboard = [[InlineKeyboardButton("🔄 Spin another track", callback_data="reroll_music")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await status_msg.edit_text(suggestion, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"❌ Music Display Error: {e}")
        await status_msg.edit_text(f"⚠️ Track suggestion failed: {str(e)}")

async def book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    query = update.callback_query
    if query:
        await query.answer()
        logger.info(f"▶️ User {update.effective_chat.id} triggered re-roll for /book")
        keywords = context.user_data.get('last_book', 'a cozy mystery')
    else:
        logger.info(f"▶️ User {update.effective_chat.id} triggered /book")
        keywords = " ".join(context.args)
        context.user_data['last_book'] = keywords
        
    if not keywords:
        usage_text = (
            "⚠️ <b>Usage:</b> /book [genre/vibe/topic]\n"
            "<i>Examples:</i>\n"
            "• <code>/book sci-fi with philosophical themes</code>\n"
            "• <code>/book livre de philosophie</code>\n"
            "• <code>/book something to make me smarter about money</code>"
        )
        await update.effective_message.reply_text(usage_text, parse_mode=ParseMode.HTML)
        return

    safe_keywords = html.escape(keywords)
    status_msg = await update.effective_message.reply_text(
        f"📚 <i>Browsing the library for '{safe_keywords}'...</i>", 
        parse_mode=ParseMode.HTML
    )
    
    prompt = f"""
    [ROLE]
    You are an elite, highly opinionated Literary Curator and Librarian. 

    [CONTEXT]
    The user wants a book recommendation based on these vibes: "{keywords}"
    
    [TASK]
    Suggest ONE perfect book (fiction or non-fiction based on the prompt).

    [STRICT INSTRUCTIONS]
    1. QUALITY: Pick a genuinely great book. Avoid high-school reading list clichés unless requested.
    2. THE PITCH: Write exactly 1 or 2 sentences explaining the plot and why it fits their vibe.
    3. PLAIN TEXT ONLY: Absolutely NO HTML tags.
    4. NO MARKDOWN: Absolutely NO asterisks (*) or hashtags (#).
    5. LANGUAGE SYNC: You MUST reply entirely in the language the user used (e.g., if French, the whole response must be in French).

    [OUTPUT STRUCTURE]
    [Book Title] by [Author] ([Year])
    [Translated word for "Genre"]: [Genre]
    
    [Translated word for "Pitch"]: [Your 1-2 sentence pitch]
    """
    
    prompt += get_lang_rule(context)
    suggestion = await ask_llm(prompt) 
    
    keyboard = [[InlineKeyboardButton("🔄 Turn the page", callback_data="reroll_book")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await status_msg.edit_text(suggestion, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"❌ Book Display Error: {e}")
        await status_msg.edit_text(f"⚠️ Book suggestion failed: {str(e)}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logger.error(f"❌ Telegram API Error: {context.error}")