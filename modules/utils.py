import re
import os
import logging
from telegram import Update
from config import AUTHORIZED_USERS

logger = logging.getLogger(__name__)

# ==========================================
# UTILITY FUNCTIONS
# ==========================================
def is_authorized(update: Update) -> bool:
    """Checks if the user sending the message is in the allowed list."""
    user_id = update.effective_user.id
    if user_id in AUTHORIZED_USERS:
        return True
    
    logger.warning(f"🚫 Unauthorized access attempt by user {user_id}")
    return False

def get_lang_rule(context) -> str:
    """ Returns a string rule to guide the LLM's language choice."""
    lang = context.user_data.get('language', 'French/English')
    
    return f"\n[LANGUAGE RULE]: Always respond in the language used by the user. " \
           f"If the request is in French, answer in French. If in English, answer in English. " \
           f"Current preferred context: {lang}."

def parse_time_string(time_str: str) -> int:
    """
    Converts a time string like '15m', '2h', '30s' into total seconds.
    Returns 0 if the format is invalid.
    """
    if not time_str:
        return 0
        
    match = re.match(r"(\d+)([smhSMH])", time_str.strip())
    if not match:
        return 0
        
    value, unit = match.groups()
    value = int(value)
    unit = unit.lower()
    
    if unit == 's':
        return value
    elif unit == 'm':
        return value * 60
    elif unit == 'h':
        return value * 3600
    
    return 0