import os
import asyncio
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from modules.intent_router import voice_handler, message_handler
from modules.database import init_db
from modules.config import TOKEN

from commands.general import start_command, error_handler
from commands.finance_news import portfolio_command, news_command
from commands.knowledge_util import research_command, weather_command, remind_command, time_command
from commands.shared_life import grocery_command, grocery_remove_command, grocery_empty_command, grocery_callback_handler, decide_command, recipe_command
from commands.health_fitness import train_command, stats_command
from commands.fun_extras import movie_command, music_command, book_command, cat_command, dateidea_command

# ==========================================
# HEALTH CHECK SERVER
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
# BOT INSTANCE
# ==========================================
def run_bot():
    """Builds and runs the bot in an isolated scope to prevent Event Loop crashes."""
    logger.info("🤖 Starting Modular MattouBot...")
    app = Application.builder().token(TOKEN).build()
    
    # --- General & Help ---
    app.add_handler(CommandHandler("start", start_command))
    
    # --- Finance & News ---
    app.add_handler(CommandHandler("portfolio", portfolio_command))
    app.add_handler(CommandHandler("news", news_command))
    
    # --- Knowledge & Utility ---
    app.add_handler(CommandHandler("research", research_command))
    app.add_handler(CommandHandler("weather", weather_command))
    app.add_handler(CommandHandler("remind", remind_command))
    app.add_handler(CommandHandler("remind", time_command))
    
    # --- Shared Life ---
    app.add_handler(CommandHandler("grocery", grocery_command))
    app.add_handler(CommandHandler("grocery_remove", grocery_remove_command))
    app.add_handler(CommandHandler("grocery_empty", grocery_empty_command))
    app.add_handler(CallbackQueryHandler(grocery_callback_handler, pattern="^g_"))
    app.add_handler(CommandHandler("decide", decide_command))
    app.add_handler(CommandHandler("recipe", recipe_command))
    app.add_handler(CallbackQueryHandler(recipe_command, pattern="^reroll_recipe$"))
    
    # --- Health ---
    app.add_handler(CommandHandler("train", train_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
    # --- Fun & Extras ---
    app.add_handler(CommandHandler("dateidea", dateidea_command))
    app.add_handler(CallbackQueryHandler(dateidea_command, pattern="^reroll_dateidea$"))
    app.add_handler(CommandHandler("cat", cat_command))
    app.add_handler(CallbackQueryHandler(cat_command, pattern="^reroll_cat$"))
    app.add_handler(CommandHandler("movie", movie_command))
    app.add_handler(CallbackQueryHandler(movie_command, pattern="^reroll_movie$"))
    app.add_handler(CommandHandler("music", music_command))
    app.add_handler(CallbackQueryHandler(music_command, pattern="^reroll_music$"))
    app.add_handler(CommandHandler("book", book_command))
    app.add_handler(CallbackQueryHandler(book_command, pattern="^reroll_book$"))

    # --- Voice Integration ---
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))
    
    app.add_error_handler(error_handler)
    
    logger.info("✅ Polling started successfully.")
    app.run_polling(drop_pending_updates=True)

# ==========================================
# MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    logger = logging.getLogger(__name__)

    threading.Thread(target=run_health_check, daemon=True).start()
    asyncio.run(init_db())
    
    if not TOKEN:
        logger.error("❌ TELEGRAM_TOKEN missing in environment variables!")
    else:
        try:
            run_bot()
        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped manually by user.")
        except Exception as e:
            logger.error(f"❌ Critical App Crash: {e}")
