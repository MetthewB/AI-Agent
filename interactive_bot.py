import os
import requests
import yfinance as yf
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- Constants ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
# Grab your Chat ID to make sure no one else can use your bot!
AUTHORIZED_USER = int(os.environ.get("TELEGRAM_CHAT_ID", 0)) 

PORTFOLIO_MAP = {
    "EUNL.DE": "MSCI World (EUNL)",
    "EUNM.DE": "MSCI Emerging Mkts (EUNM)",
    "ACM9.DE": "MSCI World SRI (ACM9)",
    "XAUUSD=X": "Gold (XAU)"
}

# --- Fake Web Server to keep Render & Cron-job happy ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        message = b"OK"
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.send_header('Content-Length', str(len(message)))
        self.end_headers()
        self.wfile.write(message)

def run_health_check():
    port = int(os.environ.get("PORT", 10000)) 
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"🌍 Web server listening on port {port}...")
    server.serve_forever()

# --- Security Helper ---
def is_authorized(update: Update) -> bool:
    """Check if the person messaging the bot is actually you."""
    return update.effective_chat.id == AUTHORIZED_USER

# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("🛑 Access Denied.")
        return
        
    welcome_text = (
        "Bonjour Matthew! 🇨🇭 I am your Lausanne Assistant.\n\n"
        "Commands:\n"
        "/portfolio - Live status of EUNL, EUNM, ACM9, Gold\n"
        "/news - Quick world & Swiss geopolitics update\n"
        "/cat - Instant cat GIF break 🐾"
    )
    await update.message.reply_text(welcome_text)

async def portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    await update.message.reply_text("Checking the markets... ⏳")
    stats = []
    for ticker, name in PORTFOLIO_MAP.items():
        try:
            # yfinance handles its own internal timeouts gracefully
            data = yf.Ticker(ticker).history(period="2d")
            current = data['Close'].iloc[-1]
            prev = data['Close'].iloc[-2]
            pct = ((current - prev) / prev) * 100
            stats.append(f"{name}: {current:.2f} ({pct:+.2f}%)")
        except Exception as e:
            stats.append(f"⚠️ Error fetching {name}")
            print(f"Portfolio error for {ticker}: {e}")
    
    response = "📈 Live Portfolio:\n" + "\n".join(stats)
    await update.message.reply_text(response)

async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    await update.message.reply_text("Scanning headlines... 🌍")
    try:
        # 1. Use Google News RSS to bypass IP blocks
        url = "https://news.google.com/rss/search?q=geopolitics+Switzerland+France+when:1d&hl=en-US&gl=US&ceid=US:en"
        
        # 2. Strict 10-second timeout
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.content, "xml") 
        items = soup.find_all("item", limit=3)
        
        if items:
            headlines = [f"• {item.title.text}" for item in items]
            response = "📰 Latest Major Events:\n\n" + "\n\n".join(headlines)
        else:
            response = "📰 No major events found in the last 24 hours."
            
        await update.message.reply_text(response)
        
    except requests.exceptions.Timeout:
        await update.message.reply_text("⚠️ News servers are responding too slowly right now. Try again later.")
    except Exception as e:
        await update.message.reply_text("⚠️ Could not fetch the news at this moment.")
        print(f"News fetch error: {e}")

async def cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    try:
        # Added strict 10-second timeout here as well!
        res = requests.get("https://api.thecatapi.com/v1/images/search?mime_types=gif", timeout=10).json()
        await update.message.reply_animation(res[0]['url'], caption="Voila! 🐾")
    except requests.exceptions.Timeout:
        await update.message.reply_text("⚠️ The cat API took too long to respond.")
    except Exception as e:
        await update.message.reply_text("The cats are sleeping. 😴")
        print(f"Cat fetch error: {e}")

# --- Main Setup ---
if __name__ == "__main__":
    threading.Thread(target=run_health_check, daemon=True).start()
    
    if not TOKEN:
        print("❌ No Telegram Token found! Check Render Environment Variables.")
    else:
        print("🤖 Telegram Bot is waking up...")
        app = Application.builder().token(TOKEN).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("portfolio", portfolio))
        app.add_handler(CommandHandler("news", news))
        app.add_handler(CommandHandler("cat", cat))
        
        app.run_polling()