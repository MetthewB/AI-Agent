import os
import requests
import yfinance as yf
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from ddgs import DDGS

# --- Constants ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
PORTFOLIO_MAP = {
    "EUNL.DE": "MSCI World (EUNL)",
    "EUNM.DE": "MSCI Emerging Mkts (EUNM)",
    "ACM9.DE": "MSCI World SRI (ACM9)",
    "XAUUSD=X": "Gold (XAU)"
}

# --- Fake Web Server to keep Render & Cron-job happy ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is alive and kicking!")

def run_health_check():
    # Render assigns a random port, we MUST use it!
    port = int(os.environ.get("PORT", 10000)) 
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"🌍 Web server listening on port {port}...")
    server.serve_forever()

# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "Bonjour Matthew! 🇨🇭 I am your Lausanne Assistant.\n\n"
        "Commands:\n"
        "/portfolio - Live status of EUNL, EUNM, ACM9, Gold\n"
        "/news - Quick world & Swiss geopolitics update\n"
        "/cat - Instant cat GIF break 🐾"
    )
    await update.message.reply_text(welcome_text)

async def portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Checking the markets... ⏳")
    stats = []
    for ticker, name in PORTFOLIO_MAP.items():
        try:
            data = yf.Ticker(ticker).history(period="2d")
            current = data['Close'].iloc[-1]
            prev = data['Close'].iloc[-2]
            pct = ((current - prev) / prev) * 100
            stats.append(f"{name}: {current:.2f} ({pct:+.2f}%)")
        except:
            stats.append(f"Error fetching {name}")
    
    response = "📈 Live Portfolio:\n" + "\n".join(stats)
    await update.message.reply_text(response)

async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Scanning headlines... 🌍")
    results = DDGS().news("Top geopolitics world Switzerland France", timelimit="d", max_results=3)
    headlines = [f"• {r['title']}" for r in results]
    response = "📰 Latest Major Events:\n\n" + "\n".join(headlines)
    await update.message.reply_text(response)

async def cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = requests.get("https://api.thecatapi.com/v1/images/search?mime_types=gif").json()
        await update.message.reply_animation(res[0]['url'], caption="Voila! 🐾")
    except:
        await update.message.reply_text("The cats are sleeping. 😴")

# --- Main Setup ---
if __name__ == "__main__":
    # 1. Start the fake web server in the background
    threading.Thread(target=run_health_check, daemon=True).start()
    
    # 2. Start the Telegram Bot
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