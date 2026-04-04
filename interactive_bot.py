import os
import re
import time
import random
import asyncio
import logging
import datetime
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
import yfinance as yf
from bs4 import BeautifulSoup
from huggingface_hub import AsyncInferenceClient
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

# ==========================================
# 1. LOGGING & SETUP
# ==========================================
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# 2. CONFIGURATION & VIP LIST
# ==========================================
TOKEN = os.environ.get("TELEGRAM_TOKEN")
HF_TOKEN = os.environ.get("HF_TOKEN")
CHAT_ID_ENV = os.environ.get("TELEGRAM_CHAT_ID", "0")

AUTHORIZED_USERS = []
for uid in CHAT_ID_ENV.split(","):
    clean_uid = uid.strip()
    if clean_uid.replace("-", "").isdigit():
        AUTHORIZED_USERS.append(int(clean_uid))

logger.info(f"✅ VIP List Loaded: {AUTHORIZED_USERS}")

# ==========================================
# 3. AI CLIENT & DATA MAPS
# ==========================================
llm_client = AsyncInferenceClient(model="Qwen/Qwen2.5-Coder-32B-Instruct", token=HF_TOKEN)

GROCERY_FILE = "groceries.txt"

PORTFOLIO_MAP = {
    "EUNL.DE": "MSCI World (EUNL)",
    "EUNM.DE": "MSCI Emerging Mkts (EUNM)",
    "ACM9.DE": "MSCI World SRI (ACM9)",
    "GLD": "Gold (XAU)"
}

WMO_WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Foggy", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Light snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Light showers", 81: "Moderate showers", 82: "Heavy showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Heavy thunderstorm"
}

# ==========================================
# 4. CORE UTILITY FUNCTIONS
# ==========================================
async def ask_llm(prompt: str) -> str:
    """Sends a prompt to the HuggingFace LLM asynchronously with a timeout."""
    try:
        logger.info("🧠 Sending prompt to HuggingFace LLM...")
        messages = [{"role": "user", "content": prompt}]
        
        response = await asyncio.wait_for(
            llm_client.chat_completion(messages=messages, max_tokens=400, temperature=0.7),
            timeout=15.0
        )
        logger.info("✅ LLM response generated successfully.")
        return response.choices[0].message.content
    except asyncio.TimeoutError:
        logger.error("❌ LLM Error: Request timed out.")
        return "<i>My AI brain took too long to think! The servers are busy, please try again.</i>"
    except Exception as e:
        logger.error(f"❌ LLM Error: {e}")
        return "<i>Sorry, my AI brain is a bit foggy right now.</i>"

def is_authorized(update: Update) -> bool:
    """Checks if the user is in the authorized VIP list."""
    chat_id = update.effective_chat.id
    if chat_id in AUTHORIZED_USERS:
        return True
    logger.warning(f"🛑 UNAUTHORIZED ACCESS ATTEMPT from ID: {chat_id}")
    return False

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
# 5. HEALTH CHECK SERVER (RENDER KEEP-AWAKE)
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        response_content = b"OK"
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.send_header('Content-Length', str(len(response_content)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(response_content)
    def log_message(self, format, *args): return

def run_health_check():
    port = int(os.environ.get("PORT", 10000)) 
    logger.info(f"🌐 Starting health check server on port {port}")
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# ==========================================
# 6. BOT COMMAND HANDLERS
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
        "• /grocery_empty - Clear the list\n"
        "• /decide [A], [B] - Settle an argument\n"
        "• /recipe [ingredients] - Empty fridge chef\n\n"
        "<b>🎉 Fun & Extras</b>\n"
        "• /cat - Instant feline dopamine\n"
        "• /dateidea [city] - Generate a date idea\n"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

# --- Finance & News ---

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
        summary = await ask_llm(prompt)
        await status_msg.edit_text(f"📰 <b>Geopolitical Briefing</b>\n\n{summary.replace('*', '')}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ News Error: {e}")
        await status_msg.edit_text("⚠️ <i>News summary failed. Try /portfolio instead?</i>", parse_mode=ParseMode.HTML)

# --- Knowledge & Utility ---

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
            
        analysis = await ask_llm(prompt)
        await status_msg.edit_text(f"📝 <b>Research Summary: {query}</b>\n\n{analysis.replace('*', '')}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Research error: {e}")
        await status_msg.edit_text("⚠️ <i>Research failed. My brain is a bit tired.</i>", parse_mode=ParseMode.HTML)

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /weather")
    
    city_query = " ".join(context.args)
    
    if city_query:
        status_msg = await update.message.reply_text(f"<i>Looking for {city_query} on the map...</i> 🌍", parse_mode=ParseMode.HTML)
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_query}&count=1&language=en&format=json"
        try:
            geo_res = await asyncio.to_thread(requests.get, geo_url, timeout=10)
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

    weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    
    try:
        res = await asyncio.to_thread(requests.get, weather_url, timeout=10)
        data = res.json()
        current = data['current_weather']
        temp = current['temperature']
        code = current['weathercode']
        
        condition = WMO_WEATHER_CODES.get(code, "mixed weather")
        
        prompt = f"""
        The current weather in {display_name} is {temp}°C with {condition}. 
        Write a short, 2-sentence cute and slightly sassy weather report for a couple. 
        Advise them on what to wear or if it's a good day to stay inside.
        Format the output cleanly using HTML <b> tags for the temperature. No markdown asterisks.
        """
        
        forecast = await ask_llm(prompt)
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

# --- Shared Life ---

async def grocery_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /grocery")
    item = " ".join(context.args)
    
    if not item:
        try:
            with open(GROCERY_FILE, "r") as f:
                items = f.read().splitlines()
            if not items:
                await update.message.reply_text("🛒 <b>The grocery list is currently empty!</b>", parse_mode=ParseMode.HTML)
            else:
                formatted_list = "\n".join([f"• {i}" for i in items])
                await update.message.reply_text(f"🛒 <b>Shared Shopping List:</b>\n\n{formatted_list}", parse_mode=ParseMode.HTML)
        except FileNotFoundError:
            await update.message.reply_text("🛒 <b>The grocery list is currently empty!</b>", parse_mode=ParseMode.HTML)
        return

    try:
        with open(GROCERY_FILE, "a") as f:
            f.write(item + "\n")
        await update.message.reply_text(f"✅ Added <b>{item}</b> to the list!", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Grocery Add Error: {e}")
        await update.message.reply_text("⚠️ <i>Failed to add the item. The cart is stuck!</i>", parse_mode=ParseMode.HTML)

async def grocery_empty_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /grocery_empty")
    try:
        if os.path.exists(GROCERY_FILE):
            os.remove(GROCERY_FILE)
            await update.message.reply_text("🧹 <b>Grocery list cleared!</b> Happy cooking! 🍳", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("🛒 <b>The list was already empty!</b>", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Grocery Clear Error: {e}")
        await update.message.reply_text("⚠️ <i>Failed to clear the list!</i>", parse_mode=ParseMode.HTML)

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
    recipe_output = await ask_llm(prompt)
    try:
        await status_msg.edit_text(recipe_output, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ HTML Parsing Error in Recipe: {e}")
        await status_msg.edit_text(
            f"👨‍🍳 <b>Here is your recipe!</b> (<i>HTML formatting disabled due to an AI glitch</i>):\n\n{recipe_output}", 
            parse_mode=None
        )

# --- Fun & Extras ---

async def dateidea_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /dateidea")
    
    location_query = " ".join(context.args)
    status_msg = await update.message.reply_text("<i>Checking the weather and thinking of something romantic...</i> 🍷", parse_mode=ParseMode.HTML)
    current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")
    
    if location_query:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location_query}&count=1&language=en&format=json"
        try:
            geo_res = await asyncio.to_thread(requests.get, geo_url, timeout=10)
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
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        res = await asyncio.to_thread(requests.get, url, timeout=10)
        data = res.json()
        temp = data['current_weather']['temperature']
        code = data['current_weather']['weathercode']
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

# ==========================================
# 7. MAIN INVINCIBLE LOOP
# ==========================================
if __name__ == "__main__":
    threading.Thread(target=run_health_check, daemon=True).start()
    
    if not TOKEN:
        logger.error("❌ TELEGRAM_TOKEN missing!")
    else:
        while True:
            try:
                logger.info("🤖 Building and starting MattouBot...")
                app = Application.builder().token(TOKEN).build()
                
                # --- General & Help ---
                app.add_handler(CommandHandler("start", start_command))
                app.add_handler(CommandHandler("help", help_command))
                
                # --- Finance & News ---
                app.add_handler(CommandHandler("portfolio", portfolio_command))
                app.add_handler(CommandHandler("news", news_command))
                
                # --- Knowledge & Utility ---
                app.add_handler(CommandHandler("research", research_command))
                app.add_handler(CommandHandler("weather", weather_command))
                app.add_handler(CommandHandler("remind", remind_command))
                
                # --- Shared Life ---
                app.add_handler(CommandHandler("grocery", grocery_command))
                app.add_handler(CommandHandler("grocery_empty", grocery_empty_command))
                app.add_handler(CommandHandler("decide", decide_command))
                app.add_handler(CommandHandler("recipe", recipe_command))
                
                # --- Fun & Extras ---
                app.add_handler(CommandHandler("dateidea", dateidea_command))
                app.add_handler(CommandHandler("cat", cat_command))
                
                app.add_error_handler(error_handler)
                
                logger.info("✅ Polling started successfully.")
                app.run_polling(drop_pending_updates=True)
                
            except Exception as e:
                logger.error(f"❌ Critical App Crash: {e}")
            
            logger.warning("⚠️ Bot stopped! Rebuilding in 10 seconds...")
            time.sleep(10)