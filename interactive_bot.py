import os
import time
import requests
import threading
import logging
import yfinance as yf
from http.server import BaseHTTPRequestHandler, HTTPServer
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from huggingface_hub import InferenceClient

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
HF_TOKEN = os.environ.get("HF_TOKEN")
CHAT_ID_ENV = os.environ.get("TELEGRAM_CHAT_ID", "0")

AUTHORIZED_USERS = []
for uid in CHAT_ID_ENV.split(","):
    clean_uid = uid.strip()
    if clean_uid.replace("-", "").isdigit():
        AUTHORIZED_USERS.append(int(clean_uid))

logger.info(f"✅ VIP List Loaded: {AUTHORIZED_USERS}")

# Initialize HF Client
llm_client = InferenceClient(model="Qwen/Qwen2.5-Coder-32B-Instruct", token=HF_TOKEN)

PORTFOLIO_MAP = {
    "EUNL.DE": "MSCI World (EUNL)",
    "EUNM.DE": "MSCI Emerging Mkts (EUNM)",
    "ACM9.DE": "MSCI World SRI (ACM9)",
    "GLD": "Gold (XAU)"
}

# --- AI Brain Function ---
def ask_llm(prompt: str) -> str:
    try:
        logger.info("🧠 Sending prompt to HuggingFace LLM...")
        messages = [{"role": "user", "content": prompt}]
        response = llm_client.chat_completion(messages=messages, max_tokens=400, temperature=0.3)
        logger.info("✅ LLM response generated successfully.")
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"❌ LLM Error: {e}")
        return "Sorry, my AI brain is a bit foggy right now."

# --- Health Check Server ---
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

def is_authorized(update: Update) -> bool:
    chat_id = update.effective_chat.id
    if chat_id in AUTHORIZED_USERS:
        return True
    else:
        logger.warning(f"🛑 UNAUTHORIZED ACCESS ATTEMPT from ID: {chat_id}")
        return False

# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /start")
    
    welcome = (
        "Hello! I am MattouBot, meow.\n\n"
        "/portfolio - Live market status\n"
        "/news - Geopolitical summary\n"
        "/weather - Lausanne current conditions\n"
        "/research [topic] - Deep dive on any topic\n"
        "/cat - Instant cat GIF break"
    )
    await update.message.reply_text(welcome)

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
        await update.message.reply_text(f"It is currently {temp}°C in Lausanne. Conditions: {condition.lower()}. 🏔️")
        
    except Exception as e:
        logger.error(f"❌ Weather Command Error: {e}")
        await update.message.reply_text("⚠️ Weather data is temporarily unavailable. Check the window! 🪟")

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
                stats.append(f"• {name}: {current:.2f} ({pct:+.2f}%)")
            else:
                stats.append(f"• {name}: ⚠️ Market closed or empty data")
                
        except Exception as e:
            logger.error(f"❌ Portfolio Error for {ticker}: {e}")
            stats.append(f"• {name}: ⚠️ Fetch failed")
            
    await update.message.reply_text("📈 Live Portfolio:\n" + "\n".join(stats))

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /news")
    await update.message.reply_text("Analyzing the news... ⏳")
    
    raw_news = []
    queries = ["geopolitics world", "geopolitics Switzerland", "geopolitics France"]
    
    try:
        for q in queries:
            url = f"https://news.google.com/rss/search?q={q}+when:1d&hl=en-US&gl=US&ceid=US:en"
            res = requests.get(url, timeout=10)
            soup = BeautifulSoup(res.content, "xml")
            items = soup.find_all("item", limit=2)
            for item in items:
                raw_news.append(item.title.text)
        
        news_context = "\n".join(raw_news)
        prompt = f"""
        Summarize these news headlines into a single, natural paragraph.
        Focus only on major geopolitics for World, Switzerland, and France.
        RULES:
        - Speak like a helpful assistant.
        - Use NO MARKDOWN (no stars, no bullets).
        - Use exactly 2 emojis.
        Headlines:
        {news_context}
        """
        summary = ask_llm(prompt)
        await update.message.reply_text(summary.replace("*", ""))
    except Exception as e:
        logger.error(f"❌ News Error: {e}")
        await update.message.reply_text("⚠️ News summarized failed. Try /portfolio instead?")

async def research_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /research")
    
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Please provide a topic! Example: /research Swiss neutrality 2026")
        return

    await update.message.reply_text(f"🔍 Researching '{query}' for you...")
    
    try:
        search_url = f"https://news.google.com/rss/search?q={query}+when:7d&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(search_url, timeout=10)
        soup = BeautifulSoup(res.content, "xml")
        headlines = [item.title.text for item in soup.find_all("item", limit=5)]
        
        if headlines:
            prompt = (
                f"Analyze the following recent headlines regarding '{query}' and provide a concise, "
                f"expert 3-sentence summary of the current situation:\n\n" + "\n".join(headlines)
            )
        else:
            prompt = (
                f"Using your expert general knowledge, provide a concise 3-sentence summary "
                f"explaining the topic of '{query}'."
            )
            
        analysis = ask_llm(prompt)
        await update.message.reply_text(f"📝 Research Summary:\n\n{analysis.replace('*', '')}")
    except Exception as e:
        logger.error(f"❌ Research error: {e}")
        await update.message.reply_text("⚠️ Research failed. My brain is a bit tired.")

async def cat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /cat")
    try:
        res = requests.get("https://api.thecatapi.com/v1/images/search?mime_types=gif", timeout=10).json()
        await update.message.reply_animation(res[0]['url'])
    except Exception as e:
        logger.error(f"❌ Cat API error: {e}")
        await update.message.reply_text("The cats are sleeping. 😴")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"❌ Telegram API Error: {context.error}")

if __name__ == "__main__":
    # Start the health server in the background (this MUST stay alive!)
    threading.Thread(target=run_health_check, daemon=True).start()
    
    if not TOKEN:
        logger.error("❌ TELEGRAM_TOKEN missing!")
    else:
        # The Invincible Loop
        while True:
            try:
                logger.info("🤖 Building and starting MattouBot...")
                app = Application.builder().token(TOKEN).build()
                
                # Add all your commands back to the fresh bot
                app.add_handler(CommandHandler("start", start_command))
                app.add_handler(CommandHandler("portfolio", portfolio_command))
                app.add_handler(CommandHandler("news", news_command))
                app.add_handler(CommandHandler("weather", weather_command))
                app.add_handler(CommandHandler("research", research_command))
                app.add_handler(CommandHandler("cat", cat_command))
                
                # Start polling
                app.run_polling(drop_pending_updates=True)
                
            except Exception as e:
                logger.error(f"❌ Critical App Crash: {e}")
            
            # If run_polling() gives up (like on a 409 Conflict), we trap it here!
            logger.warning("⚠️ Bot stopped! Rebuilding in 10 seconds...")
            time.sleep(10)