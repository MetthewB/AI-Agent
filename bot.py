import os
import time
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from modules.database import init_db
from modules.config import TOKEN

from modules.commands import (
    start_command, help_command, portfolio_command, news_command,
    research_command, weather_command, remind_command,
    grocery_command, grocery_remove_command, grocery_empty_command,
    decide_command, recipe_command, train_command, stats_command,
    dateidea_command, cat_command, error_handler
)

from modules.voice_router import voice_handler

# ==========================================
# HEALTH CHECK SERVER (RENDER KEEP-AWAKE)
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args): return

def run_health_check():
    port = int(os.environ.get("PORT", 10000)) 
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# ==========================================
# BOT INSTANCE (Clean Scope)
# ==========================================
def run_bot():
    """Builds and runs the bot in an isolated scope to prevent Event Loop crashes."""
    logger.info("🤖 Starting Modular MattouBot...")
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
    app.add_handler(CommandHandler("grocery_remove", grocery_remove_command))
    app.add_handler(CommandHandler("grocery_empty", grocery_empty_command))
    app.add_handler(CommandHandler("decide", decide_command))
    app.add_handler(CommandHandler("recipe", recipe_command))
    
    # --- Health ---
    app.add_handler(CommandHandler("train", train_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
    # --- Fun & Extras ---
    app.add_handler(CommandHandler("dateidea", dateidea_command))
    app.add_handler(CommandHandler("cat", cat_command))

    # --- Voice Integration ---
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    
    app.add_error_handler(error_handler)
    
    logger.info("✅ Polling started successfully.")
    app.run_polling(drop_pending_updates=True)

# ==========================================
# MAIN INVINCIBLE LOOP
# ==========================================
if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    logger = logging.getLogger(__name__)

    threading.Thread(target=run_health_check, daemon=True).start()
    init_db()
    
    if not TOKEN:
        logger.error("❌ TELEGRAM_TOKEN missing!")
    else:
        while True:
            try:
                # Running the bot inside this function call isolates the asyncio loop
                run_bot()
            except KeyboardInterrupt:
                logger.info("🛑 Bot stopped manually by user.")
                break
            except Exception as e:
                logger.error(f"❌ Critical App Crash: {e}")
            
            logger.warning("⚠️ Bot stopped! Rebuilding in 10 seconds...")
            time.sleep(10)