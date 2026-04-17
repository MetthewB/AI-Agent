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
    chat_id = update.effective_chat.id
    if chat_id in AUTHORIZED_USERS:
        return True
    logger.warning(f"🛑 UNAUTHORIZED ACCESS ATTEMPT from ID: {chat_id}")
    return False

def get_lang_rule(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Injects a strict language rule based on the user's latest voice command."""
    pref = context.user_data.get('lang', 'en')
    lang_str = "French" if pref == "fr" else "English"
    return (
        f"\n\nCRITICAL LANGUAGE RULE:\n"
        f"- You MUST write your ENTIRE response in {lang_str}.\n"
        f"- ABSOLUTE BAN: If the user's prompt is in Spanish, German, Italian, or ANY language other than English or French, you MUST NOT fulfill the request. "
        f"You must ABORT the task and reply EXACTLY and ONLY with the phrase: '⚠️ I only speak English and French!'"
    )

def parse_time_string(time_str: str) -> int:
    """Parses strings like '10', '1.5h', '90m', '45s' into total seconds."""
    time_str = time_str.lower().strip()
    
    if time_str.replace('.', '', 1).isdigit():
        return int(float(time_str) * 60)
        
    if re.match(r'^\d+(\.\d+)?h\d+$', time_str):
        time_str += 'm'
        
    total_seconds = 0
    matches = re.findall(r'([\d\.]+)([hms])', time_str)
    
    if not matches:
        raise ValueError("Could not parse time format.")
        
    for amount, unit in matches:
        val = float(amount)
        if unit == 'h': total_seconds += val * 3600
        elif unit == 'm': total_seconds += val * 60
        elif unit == 's': total_seconds += val
        
    return int(total_seconds)


# ==========================================
# GENERAL & HELP COMMANDS
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /start")
    
    welcome = (
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
    await update.message.reply_text(welcome, parse_mode=ParseMode.HTML)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logger.error(f"❌ Telegram API Error: {context.error}")