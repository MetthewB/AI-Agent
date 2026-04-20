import re
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from modules.config import AUTHORIZED_USERS

logger = logging.getLogger(__name__)

# ==========================================
# UTILITY FUNCTIONS
# ==========================================
def is_authorized(update: Update) -> bool:
    """Checks if the user is in the authorized VIP list."""
    if not update.effective_chat:
        return False
    chat_id = update.effective_chat.id
    if chat_id in AUTHORIZED_USERS:
        return True
    
    user_name = update.effective_user.first_name if update.effective_user else "Unknown"
    logger.warning(f"🛑 UNAUTHORIZED ACCESS ATTEMPT: {user_name} (ID: {chat_id})")
    return False

def get_lang_rule(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Injects a strict language rule based on the user's latest preference."""
    pref = context.user_data.get('lang', 'en')
    lang_str = "French" if pref == "fr" else "English"
    return (
        f"\n\n[CRITICAL LANGUAGE RULE]\n"
        f"- You MUST write your ENTIRE response in {lang_str}.\n"
        f"- BILINGUAL CONTEXT: If the user speaks a language OTHER than English or French, you must ABORT and reply: '⚠️ I only speak English and French!'"
    )

def parse_time_string(time_str: str) -> int:
    """
    Robustly parses strings like '10', '1.5h', '90m', '45s' into total seconds.
    Supports combined formats like '1h30m'.
    """
    time_str = time_str.lower().strip().replace(' ', '')
    
    if time_str.isdigit():
        return int(time_str) * 60
        
    total_seconds = 0
    patterns = {
        'h': 3600,
        'm': 60,
        's': 1
    }
    
    found_any = False
    for unit, multiplier in patterns.items():
        match = re.search(r'([\d\.]+)' + unit, time_str)
        if match:
            total_seconds += float(match.group(1)) * multiplier
            found_any = True
            
    if not found_any:
        try:
            return int(float(time_str) * 60)
        except ValueError:
            raise ValueError(f"Invalid time format: {time_str}")
        
    return int(total_seconds)


# ==========================================
# GENERAL & HELP COMMANDS
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The landing page of the bot. Returns the text for memory logging."""
    if not is_authorized(update): return None
    logger.info(f"▶️ User {update.effective_chat.id} triggered /start")
    
    welcome_text = (
        "<b>Hello! I am MattouBot, meow.</b> 🐾\n\n"
        "Here is what I can do for you:\n\n"
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
        "• /movie [topic] - Recommend a movie\n"
        "• /music [topic] - Recommend a song/album/playlist\n"
        "• /book [topic] - Recommend a book/novel"
    )
    
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)
    return "Displayed the help menu and command list."

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error for the developer."""
    logger.error(f"❌ Telegram API Error: {context.error}")