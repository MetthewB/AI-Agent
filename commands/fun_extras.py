import html
import time
import random
import asyncio
import logging
import datetime
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from modules.ai_core import ask_llm
from modules.utils import get_lang_rule, is_authorized 

logger = logging.getLogger(__name__)

# ==========================================
# FUN & EXTRAS COMMANDS
# ==========================================
async def dateidea_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    query = update.callback_query
    if query:
        await query.answer()
        logger.info(f"▶️ User {update.effective_chat.id} triggered re-roll for /dateidea")
        location_query = context.user_data.get('last_dateidea', 'the Vaud/Valais region of Switzerland')
    else:
        logger.info(f"▶️ User {update.effective_chat.id} triggered /dateidea")
        location_query = " ".join(context.args) or "the Vaud/Valais region of Switzerland"
        context.user_data['last_dateidea'] = location_query
        
    display_location = location_query.title()
    safe_display = html.escape(location_query.title())
    status_msg = await update.effective_message.reply_text(f"<i>Thinking of something romantic in {safe_display}...</i> 🍷", parse_mode=ParseMode.HTML)
    current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")
    
    weather_condition = "Unknown"
    temp = "Unknown"
    
    try:
        url = f"https://wttr.in/{location_query}?format=j1"
        headers = {"User-Agent": "MattouBot/1.0 (Telegram Assistant)"}
        res = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            temp = data['current_condition'][0]['temp_C']
            weather_condition = data['current_condition'][0]['weatherDesc'][0]['value'].lower()
    except Exception as e:
        logger.error(f"Weather fetch failed for dateidea: {e}")

    vibes = ["cozy and relaxed", "adventurous outdoors", "cultural and artistic", "foodie focused", "budget-friendly"]
    vibe = random.choice(vibes)
    
    prompt = f"""
    [ROLE]
    You are a creative, thoughtful Romantic Concierge with deep expertise in local events.

    [CONTEXT]
    - Location: {display_location}
    - Today's Date: {current_date}
    - Current Weather: {temp}°C, {weather_condition}
    - Requested Vibe: {vibe}
    
    [TASK]
    Suggest one unique, specific, and fun date idea tailored perfectly to the context.

    [STRICT INSTRUCTIONS]
    1. WEATHER GROUNDING: If raining/cold, the date must be indoors. If sunny, prioritize outdoors.
    2. SEASONAL AWARENESS: Ensure the activity is possible on {current_date}. 
    3. LOCAL LOGIC: The activity must be geographically relevant to {display_location}. No generic parks.
    4. PLAIN TEXT ONLY: Absolutely NO HTML tags.
    5. NO MARKDOWN: Absolutely NO asterisks (*) or hashtags (#). Use ALL CAPS for the title.
    6. EMOJIS: Use exactly 2 or 3 emojis total.

    [OUTPUT STRUCTURE]
    [CATCHY TITLE IN ALL CAPS] - Cost: [Free/$/$$/$$$]
    [A 2-sentence engaging description explaining the activity and why it fits the {weather_condition} weather.]
    """
    
    prompt += get_lang_rule(context)
    idea = await ask_llm(prompt) 
    
    keyboard = [[InlineKeyboardButton("🔄 Re-roll", callback_data="reroll_dateidea")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await status_msg.edit_text(f"✨ {idea}", reply_markup=reply_markup)


async def cat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    query = update.callback_query
    if query:
        await query.answer()
        logger.info(f"▶️ User {update.effective_chat.id} triggered re-roll for /cat")
    else:
        logger.info(f"▶️ User {update.effective_chat.id} triggered /cat")
        
    try:
        cat_url = f"https://api.thecatapi.com/v1/images/search?mime_types=gif"
        res = await asyncio.to_thread(requests.get, cat_url, timeout=10)
        data = res.json()
        
        keyboard = [[InlineKeyboardButton("🔄 Another cat!", callback_data="reroll_cat")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if query:
            try:
                await update.effective_message.delete()
            except Exception:
                pass
                
        await update.effective_message.reply_animation(data[0]['url'], reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"❌ Cat API error: {e}")
        await update.effective_message.reply_text("The cats are sleeping. 😴")

async def movie_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    query = update.callback_query
    if query:
        await query.answer()
        logger.info(f"▶️ User {update.effective_chat.id} triggered re-roll for /movie")
        keywords = context.user_data.get('last_movie', 'a great movie')
    else:
        logger.info(f"▶️ User {update.effective_chat.id} triggered /movie")
        keywords = " ".join(context.args)
        context.user_data['last_movie'] = keywords
        
    if not keywords:
        usage_text = (
            "⚠️ <b>Usage:</b> /movie [vibe/genre/actors]\n"
            "<i>Examples:</i>\n"
            "• <code>/movie scary with dogs but a happy ending</code>\n"
            "• <code>/movie film d'animation avec un chat</code>"
        )
        await update.effective_message.reply_text(usage_text, parse_mode=ParseMode.HTML)
        return

    safe_keywords = html.escape(keywords)
    status_text = f"🍿 <i>Searching for / Recherche de '{safe_keywords}'...</i>"
    
    if query:
        status_msg = await query.edit_message_text(status_text, parse_mode=ParseMode.HTML)
    else:
        status_msg = await update.effective_message.reply_text(status_text, parse_mode=ParseMode.HTML)
    
    current_time = time.time()
    one_week_seconds = 7 * 24 * 60 * 60
    
    if 'history_movie' not in context.user_data:
        context.user_data['history_movie'] = []
        
    context.user_data['history_movie'] = [
        item for item in context.user_data['history_movie'] 
        if (current_time - item['timestamp']) < one_week_seconds
    ]
    
    history_titles = [item['title'] for item in context.user_data['history_movie']]
    history_text = "\n".join(f"- {t}" for t in history_titles) if history_titles else "None."
    
    prompt = f"""
    [ROLE]
    You are an elite Media Sommelier.

    [CONTEXT]
    User Request: "{keywords}"

    [DO NOT RECOMMEND - RECENT SUGGESTIONS]
    You MUST NOT suggest any of the following movies or series. They have already been recommended recently:
    {history_text}

    [LANGUAGE ANCHORING - CRITICAL]
    Because these instructions are in English, you might accidentally drift into English. 
    To prevent this, you MUST begin your response by explicitly declaring the detected language of the User Request using exactly one of these tags: [LANG: EN] or [LANG: FR].
    If ambiguous, use [LANG: FR].
    After outputting the tag, write the ENTIRE rest of the response in that chosen language. Translate all labels accordingly.

    [TASK]
    Suggest ONE perfect movie or series based on the request. 
    Plain text only. No ALL CAPS titles. No Markdown (no asterisks).

    [OUTPUT STRUCTURE]
    [LANG: XX]
    🎬 Title (Year)
    [Translated 'Genre' label]: [Value]

    [Translated 'Pitch' label]: [1-2 sentence pitch]
    """
    
    suggestion = await ask_llm(prompt) 
    clean_suggestion = suggestion.replace("[LANG: FR]", "").replace("[LANG: EN]", "").strip()
    
    first_line = clean_suggestion.split('\n')[0].strip()
    if first_line and first_line not in history_titles:
        context.user_data['history_movie'].append({
            'timestamp': current_time,
            'title': first_line
        })
    
    keyboard = [[InlineKeyboardButton("🔄 Re-roll", callback_data="reroll_movie")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await status_msg.edit_text(clean_suggestion, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"❌ Movie Display Error: {e}")
        await status_msg.edit_text(f"⚠️ Erreur: {str(e)}")

async def music_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    query = update.callback_query
    if query:
        await query.answer()
        logger.info(f"▶️ User {update.effective_chat.id} triggered re-roll for /music")
        keywords = context.user_data.get('last_music', 'chill acoustic')
    else:
        logger.info(f"▶️ User {update.effective_chat.id} triggered /music")
        keywords = " ".join(context.args)
        context.user_data['last_music'] = keywords
        
    if not keywords:
        usage_text = (
            "⚠️ <b>Usage:</b> /music [genre/vibe/activity]\n"
            "<i>Examples:</i>\n"
            "• <code>/music alternative rock</code>\n"
            "• <code>/music playlist de musculation</code>"
        )
        await update.effective_message.reply_text(usage_text, parse_mode=ParseMode.HTML)
        return

    safe_keywords = html.escape(keywords)
    
    status_text = f"🎧 <i>Searching for / Recherche de '{safe_keywords}'...</i>"
    if query:
        status_msg = await query.edit_message_text(status_text, parse_mode=ParseMode.HTML)
    else:
        status_msg = await update.effective_message.reply_text(status_text, parse_mode=ParseMode.HTML)
    
    current_time = time.time()
    one_week_in_seconds = 7 * 24 * 60 * 60
    
    if 'history_music' not in context.user_data:
        context.user_data['history_music'] = []
        
    valid_history = [
        item for item in context.user_data['history_music'] 
        if (current_time - item['timestamp']) < one_week_in_seconds
    ]
    context.user_data['history_music'] = valid_history
    
    history_titles = [item['title'] for item in valid_history]
    history_text = "\n".join(f"- {title}" for title in history_titles) if history_titles else "None."

    prompt = f"""
    [ROLE]
    You are an elite DJ and Music Curator.

    [CONTEXT]
    User Request: "{keywords}"

    [DO NOT RECOMMEND - RECENT SUGGESTIONS]
    You MUST NOT suggest any of the following items. They have already been recommended recently:
    {history_text}

    [LANGUAGE ANCHORING - CRITICAL]
    Because these instructions are in English, you might accidentally drift into English. 
    To prevent this, you MUST begin your response by explicitly declaring the detected language of the User Request using exactly one of these tags: [LANG: EN] or [LANG: FR].
    If ambiguous, use [LANG: EN].
    After outputting the tag, write the ENTIRE rest of the response in that chosen language. Translate all labels accordingly.

    [TASK]
    Suggest ONE perfect song, album, or playlist. 
    Plain text only. No ALL CAPS titles. No Markdown (no asterisks). Do not output language warnings.

    [OUTPUT STRUCTURE]
    [LANG: XX]
    ♫ Title by Artist
    [Translated 'Genre' label]: [Value]

    [Translated 'Pitch/Vibe' label]: [1-2 sentence pitch]
    """
    
    suggestion = await ask_llm(prompt) 
    clean_suggestion = suggestion.replace("[LANG: FR]", "").replace("[LANG: EN]", "").strip()
    
    first_line = clean_suggestion.split('\n')[0].strip()
    if first_line and first_line not in history_titles:
        context.user_data['history_music'].append({
            'timestamp': current_time,
            'title': first_line
        })
    
    keyboard = [[InlineKeyboardButton("🔄 Spin another track", callback_data="reroll_music")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await status_msg.edit_text(clean_suggestion, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"❌ Music Display Error: {e}")
        await status_msg.edit_text(f"⚠️ Track suggestion failed: {str(e)}")

async def book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    query = update.callback_query
    if query:
        await query.answer()
        logger.info(f"▶️ User {update.effective_chat.id} triggered re-roll for /book")
        keywords = context.user_data.get('last_book', 'a cozy mystery')
    else:
        logger.info(f"▶️ User {update.effective_chat.id} triggered /book")
        keywords = " ".join(context.args)
        context.user_data['last_book'] = keywords
        
    if not keywords:
        usage_text = (
            "⚠️ <b>Usage:</b> /book [genre/vibe/topic]\n"
            "<i>Examples:</i>\n"
            "• <code>/book sci-fi with philosophical themes</code>\n"
            "• <code>/book livre de philosophie</code>"
        )
        await update.effective_message.reply_text(usage_text, parse_mode=ParseMode.HTML)
        return

    safe_keywords = html.escape(keywords)
    status_text = f"📚 <i>Searching for / Recherche de '{safe_keywords}'...</i>"
    
    if query:
        status_msg = await query.edit_message_text(status_text, parse_mode=ParseMode.HTML)
    else:
        status_msg = await update.effective_message.reply_text(status_text, parse_mode=ParseMode.HTML)
    
    current_time = time.time()
    one_week_seconds = 7 * 24 * 60 * 60
    
    if 'history_book' not in context.user_data:
        context.user_data['history_book'] = []
        
    context.user_data['history_book'] = [
        item for item in context.user_data['history_book'] 
        if (current_time - item['timestamp']) < one_week_seconds
    ]
    
    history_titles = [item['title'] for item in context.user_data['history_book']]
    history_text = "\n".join(f"- {t}" for t in history_titles) if history_titles else "None."
    
    prompt = f"""
    [ROLE]
    You are an elite Literary Curator and Librarian.

    [CONTEXT]
    User Request: "{keywords}"

    [DO NOT RECOMMEND - RECENT SUGGESTIONS]
    You MUST NOT suggest any of the following books. They have already been recommended recently:
    {history_text}

    [LANGUAGE ANCHORING - CRITICAL]
    Because these instructions are in English, you might accidentally drift into English. 
    To prevent this, you MUST begin your response by explicitly declaring the detected language of the User Request using exactly one of these tags: [LANG: EN] or [LANG: FR].
    If ambiguous, use [LANG: EN].
    After outputting the tag, write the ENTIRE rest of the response in that chosen language. Translate all labels accordingly.

    [TASK]
    Suggest ONE perfect book (fiction or non-fiction). 
    Plain text only. No ALL CAPS titles. No Markdown (no asterisks). Do not output language warnings.

    [OUTPUT STRUCTURE]
    [LANG: XX]
    📖 Title by Author (Year)
    [Translated 'Genre' label]: [Value]
    
    [Translated 'Pitch' label]: [1-2 sentence pitch]
    """
    
    suggestion = await ask_llm(prompt) 
    clean_suggestion = suggestion.replace("[LANG: FR]", "").replace("[LANG: EN]", "").strip()
    
    first_line = clean_suggestion.split('\n')[0].strip()
    if first_line and first_line not in history_titles:
        context.user_data['history_book'].append({
            'timestamp': current_time,
            'title': first_line
        })
    
    keyboard = [[InlineKeyboardButton("🔄 Turn the page", callback_data="reroll_book")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await status_msg.edit_text(clean_suggestion, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"❌ Book Display Error: {e}")
        await status_msg.edit_text(f"⚠️ Book suggestion failed: {str(e)}")