import os
import requests
import yfinance as yf
import threading
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- Configuration ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID_ENV = os.environ.get("TELEGRAM_CHAT_ID", "0")
# Clean the ID once at startup
AUTHORIZED_USER = int("".join(filter(str.isdigit, CHAT_ID_ENV)))

PORTFOLIO_MAP = {
    "EUNL.DE": "MSCI World (EUNL)",
    "EUNM.DE": "MSCI Emerging Mkts (EUNM)",
    "ACM9.DE": "MSCI World SRI (ACM9)",
    "GC=F": "Gold (XAU)"
}

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Health Check Server (Keep-Alive) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return # Silent logs to keep Render console clean

def run_health_check():
    port = int(os.environ.get("PORT", 10000)) 
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logger.info(f"🌍 Health check server active on port {port}")
    server.serve_forever()

# --- Helpers ---
def is_authorized(update: Update) -> bool:
    return update.effective_chat.id == AUTHORIZED_USER

# --- Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        logger.warning(f"Unauthorized access attempt by ID: {update.effective_chat.id}")
        await update.message.reply_text(f"🛑 Access Denied.\nYour ID: {update.effective_chat.id}")
        return

    welcome = (
        "Hello Matthew! I am Mattou bot, meow. 🐾\n\n"
        "How can I help you today?\n"
        "/portfolio - Live market status\n"
        "/news - Global & Swiss headlines\n"
        "/cat - Instant cat GIF break"
    )
    await update.message.reply_text(welcome)

async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    await update.message.reply_text("📊 Fetching market data...")
    stats = []
    
    for ticker, name in PORTFOLIO_MAP.items():
        try:
            data = yf.Ticker(ticker).history(period="2d")
            if data.empty:
                raise ValueError("No data found")
            
            current = data['Close'].iloc[-1]
            prev = data['Close'].iloc[-2]
            pct = ((current - prev) / prev) * 100
            stats.append(f"• {name}: {current:.2f} ({pct:+.2f}%)")
        except Exception as e:
            stats.append(f"• {name}: ⚠️ Data unavailable")
            logger.error(f"Error fetching {ticker}: {e}")
    
    await update.message.reply_text("📈 Live Portfolio:\n" + "\n".join(stats))

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    await update.message.reply_text("🌍 Scanning headlines...")
    try:
        url = "https://news.google.com/rss/search?q=geopolitics+Switzerland+France+when:1d&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.content, "xml") 
        items = soup.find_all("item", limit=3)
        
        if items:
            headlines = [f"• {item.title.text}" for item in items]
            response = "📰 Latest Major Events:\n\n" + "\n\n".join(headlines)
        else:
            response = "📰 No major events found in the last 24 hours."
            
        await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"News error: {e}")
        await update.message.reply_text("⚠️ Could not fetch news. Try again later.")

async def cat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    try:
        res = requests.get("https://api.thecatapi.com/v1/images/search?mime_types=gif", timeout=10).json()
        await update.message.reply_animation(res[0]['url'], caption="Voila! 🐾")
    except Exception as e:
        logger.error(f"Cat error: {e}")
        await update.message.reply_text("The cats are sleeping. 😴")

# --- Main ---
if __name__ == "__main__":
    # Start Keep-Alive Server
    threading.Thread(target=run_health_check, daemon=True).start()
    
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN not found in environment!")
    else:
        logger.info("🤖 Mattou Bot is starting...")
        app = Application.builder().token(TOKEN).build()
        
        # Add Handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("portfolio", portfolio_command))
        app.add_handler(CommandHandler("news", news_command))
        app.add_handler(CommandHandler("cat", cat_command))
        
        # Start Polling
        app.run_polling()