import os
import time
import requests
import threading
import logging
import random
import yfinance as yf
from http.server import BaseHTTPRequestHandler, HTTPServer
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from huggingface_hub import AsyncInferenceClient

# --- 1. Logging Setup ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 2. Configuration & VIP List ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
HF_TOKEN = os.environ.get("HF_TOKEN")
CHAT_ID_ENV = os.environ.get("TELEGRAM_CHAT_ID", "0")

AUTHORIZED_USERS = []
for uid in CHAT_ID_ENV.split(","):
    clean_uid = uid.strip()
    if clean_uid.replace("-", "").isdigit():
        AUTHORIZED_USERS.append(int(clean_uid))

logger.info(f"✅ VIP List Loaded: {AUTHORIZED_USERS}")

# --- 3. AI & Data Maps ---
llm_client = AsyncInferenceClient(model="Qwen/Qwen2.5-Coder-32B-Instruct", token=HF_TOKEN)

PORTFOLIO_MAP = {
    "EUNL.DE": "MSCI World (EUNL)",
    "EUNM.DE": "MSCI Emerging Mkts (EUNM)",
    "ACM9.DE": "MSCI World SRI (ACM9)",
    "GLD": "Gold (XAU)"
}

# --- 4. Core Functions ---
async def ask_llm(prompt: str) -> str:
    """Sends a prompt to the HuggingFace LLM asynchronously."""
    try:
        logger.info("🧠 Sending prompt to HuggingFace LLM...")
        messages = [{"role": "user", "content": prompt}]
        # 👈 Added 'await' here
        response = await llm_client.chat_completion(messages=messages, max_tokens=400, temperature=0.3)
        logger.info("✅ LLM response generated successfully.")
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"❌ LLM Error: {e}")
        return "<i>Sorry, my AI brain is a bit foggy right now.</i>"

def is_authorized(update: Update) -> bool:
    chat_id = update.effective_chat.id
    if chat_id in AUTHORIZED_USERS:
        return True
    logger.warning(f"🛑 UNAUTHORIZED ACCESS ATTEMPT from ID: {chat_id}")
    return False

# --- 5. Health Check Server (Render Keep-Awake) ---
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

# --- 6. Command Handlers ---

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
        "• /weather - Lausanne conditions\n\n"
        "<b>🎉 Fun & Extras</b>\n"
        "• /cat - Instant feline dopamine\n"
        "• /dateidea - Generate a date idea\n"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /weather")
    
    lat, lon = 46.5197, 6.6323
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    
    try:
        res = requests.get(url, timeout=10).json()
        current = res['current_weather']
        temp = current['temperature']
        code = current['weathercode']
        
        wmo_map = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Foggy", 48: "Foggy", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
            61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
            71: "Light snow", 73: "Moderate snow", 75: "Heavy snow",
            80: "Light showers", 81: "Moderate showers", 82: "Heavy showers",
            95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Heavy thunderstorm"
        }
        
        condition = wmo_map.get(code, "Mixed weather")
        weather_msg = (
            "🏔️ <b>Lausanne Weather</b>\n"
            f"Currently: <b>{temp}°C</b>\n"
            f"Conditions: <i>{condition}</i>"
        )
        await update.message.reply_text(weather_msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Weather Command Error: {e}")
        await update.message.reply_text("⚠️ <i>Weather data unavailable. Check the window!</i> 🪟", parse_mode=ParseMode.HTML)

async def dateidea_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /dateidea")
    
    # Send a temporary thinking message
    status_msg = await update.message.reply_text("<i>Thinking of something romantic...</i> 🍷", parse_mode=ParseMode.HTML)
    
    vibes = ["cozy and relaxed", "adventurous outdoors", "cultural and artistic", "foodie focused", "budget-friendly"]
    vibe = random.choice(vibes)
    
    prompt = f"""
    Suggest one unique, specific, and fun date idea for a couple living in or near the Vaud/Valais region of Switzerland.
    The vibe should be: {vibe}.
    Provide a catchy Title, a short 2-sentence description, and an estimated cost (e.g., Free, $$, $$$).
    Format the output cleanly using basic HTML tags like <b> for bolding. No markdown asterisks.
    """
    
    idea = await ask_llm(prompt)
    
    # Edit the thinking message with the final result
    await status_msg.edit_text(idea, parse_mode=ParseMode.HTML)

async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /portfolio")
    
    stats = []
    for ticker, name in PORTFOLIO_MAP.items():
        try:
            data = yf.Ticker(ticker).history(period="5d")
            if not data.empty and len(data) >= 2:
                current = data['Close'].iloc[-1]
                prev = data['Close'].iloc[-2]
                pct = ((current - prev) / prev) * 100
                # 👈 Upgraded to monospace <code> for beautiful alignment
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
            res = requests.get(url, timeout=10)
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
        # 👈 'await' added here since ask_llm is async now
        summary = await ask_llm(prompt)
        await status_msg.edit_text(f"📰 <b>Geopolitical Briefing</b>\n\n{summary.replace('*', '')}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ News Error: {e}")
        await status_msg.edit_text("⚠️ <i>News summary failed. Try /portfolio instead?</i>", parse_mode=ParseMode.HTML)

async def research_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /research")
    
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("⚠️ <b>Please provide a topic!</b>\n<i>Example: /research Swiss neutrality 2026</i>", parse_mode=ParseMode.HTML)
        return

    status_msg = await update.message.reply_text(f"🔍 <i>Researching '{query}'...</i>", parse_mode=ParseMode.HTML)
    
    try:
        search_url = f"https://news.google.com/rss/search?q={query}+when:7d&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(search_url, timeout=10)
        soup = BeautifulSoup(res.content, "xml")
        headlines = [item.title.text for item in soup.find_all("item", limit=5)]
        
        if headlines:
            prompt = (
                f"Analyze the following recent headlines regarding '{query}'. Provide a concise, "
                f"expert 3-sentence summary of the current situation. Use <b> tags for important keywords, no markdown.\n\n" + "\n".join(headlines)
            )
        else:
            prompt = (
                f"Using your expert general knowledge, provide a concise 3-sentence summary "
                f"explaining the topic of '{query}'. Use <b> tags for important keywords, no markdown."
            )
            
        analysis = await ask_llm(prompt)
        await status_msg.edit_text(f"📝 <b>Research Summary: {query}</b>\n\n{analysis.replace('*', '')}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Research error: {e}")
        await status_msg.edit_text("⚠️ <i>Research failed. My brain is a bit tired.</i>", parse_mode=ParseMode.HTML)

async def cat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /cat")
    try:
        res = requests.get("https://api.thecatapi.com/v1/images/search?mime_types=gif", timeout=10).json()
        await update.message.reply_animation(res[0]['url'])
    except Exception as e:
        logger.error(f"❌ Cat API error: {e}")
        await update.message.reply_text("<i>The cats are sleeping.</i> 😴", parse_mode=ParseMode.HTML)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"❌ Telegram API Error: {context.error}")

# --- 7. Main Invincible Loop ---
if __name__ == "__main__":
    threading.Thread(target=run_health_check, daemon=True).start()
    
    if not TOKEN:
        logger.error("❌ TELEGRAM_TOKEN missing!")
    else:
        while True:
            try:
                logger.info("🤖 Building and starting MattouBot...")
                app = Application.builder().token(TOKEN).build()
                
                # 👈 ALL commands are now properly registered here!
                app.add_handler(CommandHandler("start", start_command))
                app.add_handler(CommandHandler("help", help_command))
                app.add_handler(CommandHandler("portfolio", portfolio_command))
                app.add_handler(CommandHandler("news", news_command))
                app.add_handler(CommandHandler("weather", weather_command))
                app.add_handler(CommandHandler("research", research_command))
                app.add_handler(CommandHandler("cat", cat_command))
                app.add_handler(CommandHandler("dateidea", dateidea_command))
                
                app.add_error_handler(error_handler)
                
                logger.info("✅ Polling started successfully.")
                app.run_polling(drop_pending_updates=True)
                
            except Exception as e:
                logger.error(f"❌ Critical App Crash: {e}")
            
            logger.warning("⚠️ Bot stopped! Rebuilding in 10 seconds...")
            time.sleep(10)