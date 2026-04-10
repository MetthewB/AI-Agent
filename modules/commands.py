import re
import time
import random
import difflib
import asyncio
import logging
import datetime
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

# Import everything we need from our other modules!
from modules.config import AUTHORIZED_USERS, PORTFOLIO_MAP, WMO_WEATHER_CODES, grocery_collection
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
    return f"\n\nCRITICAL LANGUAGE RULE:\n- Write your ENTIRE response in {lang_str}.\n- Exception: If the user's explicit input is in the other supported language (English/French), seamlessly switch to that language.\n- STRICT BAN: If the user requests content in Spanish, German, Italian, or ANY language other than English or French, DO NOT fulfill the request. Reply EXACTLY with: '⚠️ I only speak English and French!'"

def parse_time_string(time_str: str) -> int:
    """Parses strings like '10', '1h30', '50s' into total seconds."""
    time_str = time_str.lower().strip()
    if time_str.isdigit():
        return int(time_str) * 60
    if re.match(r'^\d+h\d+$', time_str):
        time_str += 'm'
    total_seconds = 0
    matches = re.findall(r'(\d+)([hms])', time_str)
    if not matches:
        raise ValueError("Could not parse time format.")
    for amount, unit in matches:
        val = int(amount)
        if unit == 'h': total_seconds += val * 3600
        elif unit == 'm': total_seconds += val * 60
        elif unit == 's': total_seconds += val
    return total_seconds


# ==========================================
# GENERAL & HELP COMMANDS
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /start")
    
    welcome = (
        "<b>Hello! I am MattouBot, meow.</b> 🐾\n\n"
        "Here is what I can do for you:\n"
        "• /help - Open the command center\n"
        "• /portfolio - Live market status\n"
        "• /weather - Lausanne conditions\n"
    )
    await update.message.reply_text(welcome, parse_mode=ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /help")
    
    help_text = (
        "🐾 <b>MattouBot Command Center</b> 🐾\n\n"
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
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


# ==========================================
# FINANCE & NEWS COMMANDS
# ==========================================
async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /portfolio")
    
    stats = []
    for ticker, name in PORTFOLIO_MAP.items():
        try:
            stock = yf.Ticker(ticker)
            data = await asyncio.to_thread(stock.history, period="5d")
            
            if not data.empty and len(data) >= 2:
                current = data['Close'].iloc[-1]
                prev = data['Close'].iloc[-2]
                pct = ((current - prev) / prev) * 100
                stats.append(f"• {name}:\n  <code>{current:.2f} ({pct:+.2f}%)</code>")
            else:
                stats.append(f"• {name}:\n  <code>⚠️ Market closed</code>")
        except Exception as e:
            logger.error(f"❌ Portfolio Error for {ticker}: {e}")
            stats.append(f"• {name}:\n  <code>⚠️ Fetch failed</code>")
    
    header = "📊 <b>Live Market Portfolio</b>\n━━━━━━━━━━━━━━━━━━━\n"
    body = "\n".join(stats)
    await update.message.reply_text(f"{header}{body}", parse_mode=ParseMode.HTML)

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
        Summarize these news headlines into a single, natural paragraph.
        Focus only on major geopolitics for World, Switzerland, and France.
        RULES:
        - Speak like a helpful assistant.
        - Use NO MARKDOWN (no stars, no bullets).
        - Format key entities (countries, leaders) using HTML <b> tags.
        - Use exactly 2 emojis.
        Headlines:
        {news_context}
        """
        
        prompt += get_lang_rule(context)
        summary = await ask_llm(prompt)
        await status_msg.edit_text(f"📰 <b>Geopolitical Briefing</b>\n\n{summary.replace('*', '')}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ News Error: {e}")
        await status_msg.edit_text("⚠️ <i>News summary failed. Try /portfolio instead?</i>", parse_mode=ParseMode.HTML)


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

    status_msg = await update.message.reply_text(f"🔍 <i>Researching '{query}'...</i>", parse_mode=ParseMode.HTML)
    
    try:
        search_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        res = await asyncio.to_thread(requests.get, search_url, timeout=10)
        soup = BeautifulSoup(res.content, "xml")
        headlines = [item.title.text for item in soup.find_all("item", limit=5)]
        
        if headlines:
            headlines_text = "\n".join(headlines)
            prompt = f"""
            You are a strict, highly accurate intelligence analyst.
            Based ONLY on the following headlines, provide a 3-sentence summary of the current situation regarding '{query}'.
            
            CRITICAL RULES:
            1. You are strictly forbidden from adding outside information or guessing.
            2. If these headlines are completely irrelevant to '{query}', or too vague to summarize, DO NOT attempt to write a summary. Instead, reply EXACTLY with:
            "⚠️ <i>The recent news headlines do not contain enough relevant information to provide a reliable summary.</i>"
            3. Use <b> tags for key entities. No markdown asterisks.
            
            HEADLINES:
            {headlines_text}
            """
        else:
            prompt = f"""
            You are a strict, highly accurate research assistant. 
            Your task is to explain the topic '{query}'.
            
            CRITICAL RULES:
            1. You are strictly forbidden from guessing, assuming, or hallucinating facts.
            2. If '{query}' refers to an event where facts are not fully confirmed, state ONLY what is officially known.
            3. If you do not have enough verified factual knowledge to write a 3-sentence summary, DO NOT guess. Instead, reply EXACTLY with:
            "⚠️ <i>I do not have enough verified, reliable information in my database to summarize this topic accurately.</i>"
            
            If you DO have the facts, provide a concise 3-sentence summary using <b> tags for important keywords. No markdown asterisks.
            """
            
        prompt += get_lang_rule(context)
        analysis = await ask_llm(prompt)
        await status_msg.edit_text(f"📝 <b>Research Summary: {query}</b>\n\n{analysis.replace('*', '')}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Research error: {e}")
        await status_msg.edit_text("⚠️ <i>Research failed. My brain is a bit tired.</i>", parse_mode=ParseMode.HTML)

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /weather")
    
    city_query = " ".join(context.args)
    headers = {"User-Agent": "MattouBot/1.0 (Telegram Assistant)"}
    
    if city_query:
        status_msg = await update.message.reply_text(f"<i>Looking for {city_query} on the map...</i> 🌍", parse_mode=ParseMode.HTML)
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_query}&count=1&language=en&format=json"
        try:
            geo_res = await asyncio.to_thread(requests.get, geo_url, headers=headers, timeout=10)
            geo_data = geo_res.json()
            if "results" not in geo_data:
                await status_msg.edit_text(f"⚠️ <i>I couldn't find a city named '<b>{city_query}</b>'. Did you make a typo?</i>", parse_mode=ParseMode.HTML)
                return
            city_name = geo_data['results'][0]['name']
            country = geo_data['results'][0].get('country', '')
            display_name = f"{city_name}, {country}" if country else city_name
            lat = geo_data['results'][0]['latitude']
            lon = geo_data['results'][0]['longitude']
        except Exception as e:
            logger.error(f"❌ Geocoding Error: {e}")
            await status_msg.edit_text("⚠️ <i>My map is broken right now. Try again later!</i> 🗺️", parse_mode=ParseMode.HTML)
            return
    else:
        status_msg = await update.message.reply_text("<i>Looking out the window in Lausanne...</i> 🏔️", parse_mode=ParseMode.HTML)
        display_name = "Lausanne, Switzerland"
        lat, lon = 46.5197, 6.6323

    weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code"
    
    try:
        res = await asyncio.to_thread(requests.get, weather_url, headers=headers, timeout=10)
        data = res.json()
        
        if "error" in data:
            logger.error(f"❌ Open-Meteo API Error: {data}")
            await status_msg.edit_text("⚠️ <i>The weather radar is blocking my connection!</i>", parse_mode=ParseMode.HTML)
            return
            
        current = data['current']
        temp = current['temperature_2m']
        code = current['weather_code']
        condition = WMO_WEATHER_CODES.get(code, "mixed weather")
        
        prompt = f"""
        CONTEXT:
        Location: {display_name}
        Temperature: {temp}°C
        Conditions: {condition}

        TASK:
        Write a short, 2-sentence cute and slightly sassy weather report for a couple. 
        Advise them on what to wear or if it's a good day to stay inside.

        CRITICAL RULES:
        1. ONLY output the 2-sentence report. 
        2. DO NOT include any introductory text, self-corrections, or "Here is your report."
        3. Format the temperature ({temp}°C) using HTML <b> tags. 
        4. ABSOLUTELY NO MARKDOWN (no asterisks *).
        5. Use exactly 2 emojis.
        """
        
        prompt += get_lang_rule(context)
        forecast = await ask_llm(prompt, max_tokens=100)
        await status_msg.edit_text(f"🌍 <b>Forecast for {display_name}</b>\n\n{forecast}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Weather Command Error: {e}")
        await status_msg.edit_text("⚠️ <i>Weather data unavailable. Check the window!</i> 🪟", parse_mode=ParseMode.HTML)

async def remind_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        chat_id=job.chat_id, 
        text=f"🔔 <b>REMINDER:</b> {job.data}", 
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
        
        await update.message.reply_text(f"🕒 Got it! I will remind you to <b>{message}</b> in {time_display}.", parse_mode=ParseMode.HTML)
    except (IndexError, ValueError):
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
async def grocery_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /grocery")
    item = " ".join(context.args)
    
    if not item:
        try:
            items_cursor = grocery_collection.find()
            items = [doc["item"] for doc in items_cursor]
            
            if not items:
                await update.message.reply_text("🛒 <b>The grocery list is currently empty!</b>", parse_mode=ParseMode.HTML)
            else:
                formatted_list = "\n".join([f"• {i}" for i in items])
                await update.message.reply_text(f"🛒 <b>Shared Shopping List:</b>\n\n{formatted_list}", parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"❌ Grocery Read Error: {e}")
            await update.message.reply_text("⚠️ <i>Failed to read the list from the database!</i>", parse_mode=ParseMode.HTML)
        return

    try:
        grocery_collection.insert_one({"item": item})
        await update.message.reply_text(f"✅ Added <b>{item}</b> to the list!", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Grocery Add Error: {e}")
        await update.message.reply_text("⚠️ <i>Failed to add the item. The cart is stuck!</i>", parse_mode=ParseMode.HTML)

async def grocery_remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /grocery_remove")
    item_to_remove = " ".join(context.args).strip()
    
    if not item_to_remove:
        await update.message.reply_text("⚠️ <b>Usage:</b> /grocery_remove [item name]\n<i>Example: /grocery_remove eggs</i>", parse_mode=ParseMode.HTML)
        return
        
    try:
        items_cursor = grocery_collection.find()
        current_items = [doc["item"] for doc in items_cursor]
        
        if not current_items:
            await update.message.reply_text("🛒 <b>The list is already empty!</b>", parse_mode=ParseMode.HTML)
            return
        
        matches = difflib.get_close_matches(item_to_remove, current_items, n=1, cutoff=0.3)
        
        if matches:
            best_match = matches[0]
            grocery_collection.delete_one({"item": best_match})
            await update.message.reply_text(f"✅ Removed <b>{best_match}</b> from the list!", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"⚠️ I couldn't find anything resembling <b>{item_to_remove}</b> in the list.", parse_mode=ParseMode.HTML)
            
    except Exception as e:
        logger.error(f"❌ Grocery Remove Error: {e}")
        await update.message.reply_text("⚠️ <i>Failed to remove the item from the database!</i>", parse_mode=ParseMode.HTML)

async def grocery_empty_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /grocery_empty")
    
    try:
        result = grocery_collection.delete_many({})
        if result.deleted_count > 0:
            await update.message.reply_text(f"🧹 <b>Grocery list cleared!</b> ({result.deleted_count} items removed) Happy cooking! 🍳", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("🛒 <b>The list was already empty!</b>", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Grocery Clear Error: {e}")
        await update.message.reply_text("⚠️ <i>Failed to clear the database!</i>", parse_mode=ParseMode.HTML)

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
    status_msg = await update.message.reply_text("⚖️ <i>The AI is weighing the options...</i>", parse_mode=ParseMode.HTML)
    await asyncio.sleep(2)
    await status_msg.edit_text(f"🎯 <b>Decision Made:</b>\n\nI have spoken. You are going with: <b>{choice}</b>", parse_mode=ParseMode.HTML)

async def recipe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /recipe")
    ingredients = " ".join(context.args)
    
    if not ingredients:
        await update.message.reply_text("⚠️ <b>Usage:</b> /recipe [ingredient 1], [ingredient 2]", parse_mode=ParseMode.HTML)
        return
        
    status_msg = await update.message.reply_text("👨‍🍳 <i>Putting on my chef's hat and reviewing your ingredients...</i>", parse_mode=ParseMode.HTML)
    prompt = f"""
    You are a Michelin-star chef helping a couple cook dinner. They only have the following ingredients available:
    {ingredients}
    
    Invent a creative, delicious, and easy-to-make recipe using mostly just these ingredients.
    
    CRITICAL RULES:
    1. Provide a catchy, appetizing Title.
    2. Provide a short "Ingredients list" and a concise step-by-step "Instructions" list.
    3. Format the output cleanly using ONLY Telegram-supported HTML tags: <b> and <i>.
    4. FORBIDDEN HTML: Do NOT use <ol>, <ul>, <li>, or <br> tags. Use standard text numbers (1., 2., 3.) or bullet points (•) for your lists.
    5. FORBIDDEN MARKDOWN: Do NOT use markdown asterisks (* or **). 
    6. Keep the tone encouraging and culinary.
    """
    prompt += get_lang_rule(context)
    recipe_output = await ask_llm(prompt)
    try:
        await status_msg.edit_text(recipe_output, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ HTML Parsing Error in Recipe: {e}")
        await status_msg.edit_text(
            f"👨‍🍳 <b>Here is your recipe!</b> (<i>HTML formatting disabled due to an AI glitch</i>):\n\n{recipe_output}", 
            parse_mode=None
        )


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
    You are an elite, highly knowledgeable personal trainer. 
    Your client wants a tailored workout.
    
    CURRENT CONTEXT:
    - Today's Date: {current_date}
    
    CLIENT REQUEST:
    Focus: {request_details}
    
    CLIENT'S RECENT STRAVA HISTORY (Format: YYYY-MM-DD):
    {history_text}
    
    SPORT SCIENCE & FATIGUE RULES (Apply these SILENTLY to design the workout, do NOT explain them in the output):
    1. Cross-Training Intelligence: You MUST differentiate between Local Fatigue (specific muscles) and Systemic Fatigue (cardiovascular).
       - If they did an upper-body "Push" or "Pull" day recently, their legs and cardio are FRESH. Do not penalize running or cycling.
       - If they did a heavy "Leg Day" yesterday, running or cycling today should be modified for active recovery.
       - If they did heavy Cardio recently, their upper body is completely fresh for weightlifting.
    2. Date Math: Compare history dates to Today's Date ({current_date}). Calculate exact rest days. Do not assume a workout was yesterday unless the dates are exactly 1 day apart.
    
    FORMATTING RULES:
    - Use ONLY basic HTML tags (<b> and <i>). 
    - ABSOLUTELY NO MARKDOWN (*, **, #). 
    - FORBIDDEN HTML: Do NOT invent fake tags like <emoji>. Do NOT use <ol>, <ul>, <li>, or <br>. Use standard text bullet points (•).
    - Use exactly 3 emojis in the entire response.
    
    REQUIRED OUTPUT STRUCTURE (You MUST use these exact headings in this precise order):
    
    <b>📊 Recent Training History</b>
    (Convert the dates from the Strava History to DD/MM format. If there is no distance, leave it out.)
    • [Date (DD/MM)]: [Sport] - [Distance]km - [Duration] mins
    
    <b>🎯 [Insert Catchy Workout Title]</b>
    
    <b>🔥 Warm-Up</b>
    • [Item 1]
    
    <b>⚡ Main Set</b>
    • [Item 1]
    
    <b>🧘 Cool-Down</b>
    • [Item 1]
    """
    
    prompt += get_lang_rule(context)
    workout = await ask_llm(prompt)
    try:
        await status_msg.edit_text(workout, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ HTML Parsing Error in Train: {e}")
        await status_msg.edit_text(
            f"🏃‍♂️ <b>Here is your workout!</b> (<i>Formatting disabled due to AI glitch</i>):\n\n{workout}", 
            parse_mode=None
        )

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
        You are an elite personal trainer. Review your client's training from the last 7 days:
        
        {stats_text}
        
        CRITICAL RULES:
        1. Write a short, 2-sentence encouraging weekly performance review based on their mix of sports.
        2. SMART GYM LOGIC: If they did gym/weight training (often labeled 'WeightTraining' or 'Workout') but have 0 Coros Load, DO NOT say they were resting. Acknowledge their hard work in the gym building strength!
        3. If Total Coros Load > 400, strictly advise them to prioritize recovery.
        4. Format the output cleanly using ONLY basic HTML tags like <b> and <i>. 
        5. ABSOLUTELY NO MARKDOWN (*, **, #). Max 2 emojis.
        6. FORBIDDEN HTML: Do NOT invent fake tags like <emoji>. Do NOT use <ol>, <ul>, <li>, or <br>.
        """
        
        prompt += get_lang_rule(context)
        ai_review = await ask_llm(prompt)
        
        final_message = f"📊 <b>7-Day Performance Review</b>\n\n{stats_text}\n\n<b>Coach's Note:</b>\n{ai_review}"
        
        try:
            await status_msg.edit_text(final_message, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"❌ HTML Parsing Error in Stats: {e}")
            await status_msg.edit_text(
                f"📊 <b>7-Day Performance Review</b> (<i>Formatting disabled due to AI glitch</i>):\n\n{stats_text}\n\nCoach's Note:\n{ai_review}", 
                parse_mode=None
            )
            
    except Exception as e:
        logger.error(f"❌ Stats Fetch Error: {e}")
        await status_msg.edit_text("⚠️ <i>Failed to fetch your weekly stats. Check the logs!</i>", parse_mode=ParseMode.HTML)


# ==========================================
# FUN & EXTRAS COMMANDS
# ==========================================
async def dateidea_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /dateidea")
    
    location_query = " ".join(context.args)
    status_msg = await update.message.reply_text("<i>Checking the weather and thinking of something romantic...</i> 🍷", parse_mode=ParseMode.HTML)
    current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")
    
    if location_query:
        headers = {"User-Agent": "MattouBot/1.0 (Telegram Assistant)"}
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location_query}&count=1&language=en&format=json"
        try:
            geo_res = await asyncio.to_thread(requests.get, geo_url, headers=headers, timeout=10)
            geo_data = geo_res.json()
            if "results" not in geo_data:
                await status_msg.edit_text(f"⚠️ <i>I couldn't find a place named '<b>{location_query}</b>'. Did you make a typo?</i>", parse_mode=ParseMode.HTML)
                return
            city_name = geo_data['results'][0]['name']
            country = geo_data['results'][0].get('country', '')
            display_location = f"{city_name}, {country}" if country else city_name
            lat = geo_data['results'][0]['latitude']
            lon = geo_data['results'][0]['longitude']
        except Exception as e:
            logger.error(f"❌ Geocoding Error for dateidea: {e}")
            await status_msg.edit_text("⚠️ <i>My map is broken right now. Try again later!</i> 🗺️", parse_mode=ParseMode.HTML)
            return
    else:
        display_location = "the Vaud/Valais region of Switzerland"
        lat, lon = 46.5197, 6.6323 

    weather_condition = "Unknown"
    temp = "Unknown"
    
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code"
        headers = {"User-Agent": "MattouBot/1.0 (Telegram Assistant)"}
        
        res = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
        data = res.json()
        
        if "error" not in data:
            temp = data['current']['temperature_2m']
            code = data['current']['weather_code']
            weather_condition = WMO_WEATHER_CODES.get(code, "mixed weather").lower()
    except Exception as e:
        logger.error(f"Weather fetch failed for dateidea: {e}")

    vibes = ["cozy and relaxed", "adventurous outdoors", "cultural and artistic", "foodie focused", "budget-friendly"]
    vibe = random.choice(vibes)
    
    prompt = f"""
    Suggest one unique, specific, and fun date idea for a couple located in or near {display_location}.
    
    CURRENT CONTEXT:
    - Today's Date: {current_date}
    - Current Weather: {temp}°C and {weather_condition}
    - Requested Vibe: {vibe}
    
    CRITICAL RULES:
    1. The date idea MUST strictly make sense for the current weather and season.
    2. Ensure the location makes geographical sense for {display_location}.
    3. Provide a catchy Title, a short 2-sentence description, and an estimated cost (e.g., Free, $$, $$$).
    4. Format the output cleanly using basic HTML tags like <b> for bolding. No markdown asterisks.
    5. EXACTLY 2 or 3 emojis must be used in your entire response. No more, no less.
    """
    
    prompt += get_lang_rule(context)
    idea = await ask_llm(prompt) 
    await status_msg.edit_text(idea, parse_mode=ParseMode.HTML)

async def cat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /cat")
    try:
        cat_url = f"https://api.thecatapi.com/v1/images/search?mime_types=gif"
        res = await asyncio.to_thread(requests.get, cat_url, timeout=10)
        data = res.json()
        await update.message.reply_animation(data[0]['url'])
    except Exception as e:
        logger.error(f"❌ Cat API error: {e}")
        await update.message.reply_text("<i>The cats are sleeping.</i> 😴", parse_mode=ParseMode.HTML)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"❌ Telegram API Error: {context.error}")