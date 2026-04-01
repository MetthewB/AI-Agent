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
    "GLD": "Gold (XAU)"
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
        success = False
        for attempt in range(3):
            try:
                data = yf.Ticker(ticker).history(period="2d")
                if not data.empty and len(data) >= 2:
                    current = data['Close'].iloc[-1]
                    prev = data['Close'].iloc[-2]
                    pct = ((current - prev) / prev) * 100
                    stats.append(f"• {name}: {current:.2f} ({pct:+.2f}%)")
                    success = True
                    break
            except Exception as e:
                logger.error(f"Attempt {attempt+1} failed for {ticker}: {e}")
            
        if not success:
            stats.append(f"• {name}: ⚠️ Data unavailable")
    
    await update.message.reply_text("📈 Live Portfolio:\n" + "\n".join(stats))

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    await update.message.reply_text("🌍 Scanning regional headlines...")
    
    # We will search for 3 specific areas to get a better mix
    queries = [
        ("GLOBAL", "geopolitics+world+news"),
        ("SWISS", "geopolitics+Switzerland"),
        ("FRANCE", "geopolitics+France")
    ]
    
    response_lines = ["📰 **Latest Major Events**", ""]
    
    try:
        for region, q in queries:
            url = f"https://news.google.com/rss/search?q={q}+when:1d&hl=en-US&gl=US&ceid=US:en"
            res = requests.get(url, timeout=10)
            soup = BeautifulSoup(res.content, "xml")
            item = soup.find("item") # Just take the top 1 for each region
            
            if item:
                # Clean up the title (remove the " - Source Name" at the end)
                full_title = item.title.text
                clean_title = full_title.split(" - ")[0]
                
                # Truncate if it's still way too long (over 100 chars)
                if len(clean_title) > 100:
                    clean_title = clean_title[:97] + "..."
                
                response_lines.append(f"📍 {region}")
                response_lines.append(f"{clean_title}")
                response_lines.append("") # Empty line for spacing
        
        final_response = "\n".join(response_lines)
        if len(response_lines) <= 2:
            final_response = "📰 No major events found in the last 24 hours."

        # REMINDER: We are using NO MARKDOWN for consistency with your earlier rules
        # If you want bold headers, you can use them, but here I've kept it plain text
        await update.message.reply_text(final_response.replace("**", ""))
        
    except Exception as e:
        logger.error(f"News error: {e}")
        await update.message.reply_text("⚠️ News servers are busy. Please try again in a moment.")

async def cat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    try:
        res = requests.get("https://api.thecatapi.com/v1/images/search?mime_types=gif", timeout=10).json()
        await update.message.reply_animation(res[0]['url'])
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