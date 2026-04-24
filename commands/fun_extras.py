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
from modules.utils import is_authorized 

logger = logging.getLogger(__name__)

# ==========================================
# FUN & EXTRAS COMMANDS
# ==========================================
async def dateidea_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    
    lang = context.user_data.get('lang', 'fr')
    
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
    safe_display = html.escape(display_location)
    
    if lang == 'fr':
        status_text = f"🍷 <i>Recherche d'une idée romantique à {safe_display}...</i>"
        btn_text = "🔄 Autre idée"
    else:
        status_text = f"🍷 <i>Thinking of something romantic in {safe_display}...</i>"
        btn_text = "🔄 Re-roll"
    
    if query:
        status_msg = await query.edit_message_text(status_text, parse_mode=ParseMode.HTML)
    else:
        status_msg = await update.effective_message.reply_text(status_text, parse_mode=ParseMode.HTML)
        
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
    
    target_lang = "FRENCH" if lang == 'fr' else "ENGLISH"
    cost_label = "Coût" if lang == 'fr' else "Cost"
    
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
    1. LANGUAGE OVERRIDE: You MUST write the ENTIRE response natively in {target_lang}. Do not drift into English if {target_lang} is FRENCH.
    2. WEATHER GROUNDING: If raining/cold, the date must be indoors. If sunny, prioritize outdoors. If weather is "Unknown", suggest a versatile all-weather idea.
    3. SEASONAL AWARENESS: Ensure the activity is possible on {current_date}. 
    4. LOCAL LOGIC: The activity must be geographically relevant to {display_location}. No generic parks.
    5. CASING: Use normal **Sentence Case** for the description. Do not capitalize every word.
    6. FORMATTING: Plain text ONLY. Absolutely NO HTML tags or Markdown (no asterisks *, no hashtags #). 
    7. EMOJIS: Use exactly 2 or 3 emojis total.

    [OUTPUT STRUCTURE]
    [Catchy Title] - {cost_label}: [Free/$/$$/$$$]
    ─────────────────
    [A 2-sentence engaging description explaining the activity and why it fits the weather and vibe.]
    """
    
    idea = await ask_llm(prompt) 
    clean_idea = idea.replace("*", "").strip()
    
    keyboard = [[InlineKeyboardButton(btn_text, callback_data="reroll_dateidea")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await status_msg.edit_text(f"✨ {clean_idea}", reply_markup=reply_markup)
        return clean_idea
    except Exception as e:
        logger.error(f"❌ Date Idea Display Error: {e}")
        err_msg = "⚠️ Échec de la génération de l'idée." if lang == 'fr' else "⚠️ Failed to generate date idea."
        await status_msg.edit_text(err_msg)
        return None


async def cat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    
    user_input = update.message.text.lower() if update.message and update.message.text else ""
    lang = context.user_data.get('lang', 'fr')
    
    if "chat" in user_input:
        lang = 'fr'
        context.user_data['lang'] = 'fr'
    elif "cat" in user_input:
        lang = 'en'
        context.user_data['lang'] = 'en'

    btn_text = "🔄 Un autre chat !" if lang == 'fr' else "🔄 Another cat!"
    err_text = "Les chats dorment. 😴" if lang == 'fr' else "The cats are sleeping. 😴"
    
    query = update.callback_query
    if query:
        await query.answer()
        logger.info(f"▶️ User {update.effective_chat.id} triggered re-roll for /cat")
    else:
        logger.info(f"▶️ User {update.effective_chat.id} triggered /cat")
        
    try:
        cat_url = "https://api.thecatapi.com/v1/images/search?mime_types=gif"
        res = await asyncio.to_thread(requests.get, cat_url, timeout=10)
        data = res.json()
        
        keyboard = [[InlineKeyboardButton(btn_text, callback_data="reroll_cat")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if query:
            try:
                await update.effective_message.delete()
            except Exception:
                pass
                
        await update.effective_message.reply_animation(data[0]['url'], reply_markup=reply_markup)
        return "Displayed a cat GIF."
        
    except Exception as e:
        logger.error(f"❌ Cat API error: {e}")
        await update.effective_message.reply_text(err_text)
        return None


async def movie_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    
    lang = context.user_data.get('lang', 'fr')
    
    query = update.callback_query
    if query:
        await query.answer()
        logger.info(f"▶️ User {update.effective_chat.id} triggered re-roll for /movie")
        keywords = context.user_data.get('last_movie', 'a great movie')
    else:
        logger.info(f"▶️ User {update.effective_chat.id} triggered /movie")
        keywords = " ".join(context.args)
        context.user_data['last_movie'] = keywords

    if keywords and not query:
        kw_lower = keywords.lower()
        if any(w in kw_lower for w in ["film", "série", "avec", "un", "une", "horreur", "comédie", "drôle", "peur"]):
            lang = 'fr'
            context.user_data['lang'] = 'fr'
        elif any(w in kw_lower for w in ["movie", "show", "with", "a", "an", "horror", "comedy", "funny", "scary"]):
            lang = 'en'
            context.user_data['lang'] = 'en'
        
    if not keywords:
        if lang == 'fr':
            usage_text = (
                "⚠️ <b>Utilisation :</b> /movie [ambiance/genre/acteurs]\n"
                "<i>Exemples :</i>\n"
                "• <code>/movie film qui fait peur avec des chiens mais une fin heureuse</code>\n"
                "• <code>/movie film d'animation avec un chat</code>"
            )
        else:
            usage_text = (
                "⚠️ <b>Usage:</b> /movie [vibe/genre/actors]\n"
                "<i>Examples:</i>\n"
                "• <code>/movie scary with dogs but a happy ending</code>\n"
                "• <code>/movie animated movie with a cat</code>"
            )
        await update.effective_message.reply_text(usage_text, parse_mode=ParseMode.HTML)
        return None

    safe_keywords = html.escape(keywords)
    
    if lang == 'fr':
        status_text = f"🍿 <i>Recherche de '{safe_keywords}'...</i>"
        btn_text = "🔄 Autre suggestion"
    else:
        status_text = f"🍿 <i>Searching for '{safe_keywords}'...</i>"
        btn_text = "🔄 Re-roll"
    
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
    
    target_lang = "FRENCH" if lang == 'fr' else "ENGLISH"
    genre_label = "Genre"
    pitch_label = "Synopsis" if lang == 'fr' else "Pitch"
    
    prompt = f"""
    [ROLE]
    You are an elite Media Sommelier.

    [CONTEXT]
    User Request: "{keywords}"

    [DO NOT RECOMMEND - RECENT SUGGESTIONS]
    You MUST NOT suggest any of the following movies or series. They have already been recommended recently:
    {history_text}

    [TASK]
    Suggest ONE perfect movie or series based on the TRUE MEANING of the request. 

    [STRICT INSTRUCTIONS]
    1. LANGUAGE OVERRIDE: You MUST write the ENTIRE recommendation natively in {target_lang}. Do not drift into English if {target_lang} is FRENCH.
    2. SEMANTIC CURATION: Interpret the *vibe*, *plot*, or *meaning* of the request. DO NOT just search for a movie with the user's exact words in the title.
    3. NO HALLUCINATIONS: You must recommend a REAL, existing, released movie or TV series. Do not invent titles, directors, or plots.
    4. CASING: Use normal **Sentence Case** for the {pitch_label}. Do NOT use Title Case for every word in the description.
    5. FORMATTING: Plain text only. No Markdown (no asterisks). Do not use brackets [] for the labels.

    [OUTPUT STRUCTURE]
    🎬 Title (Year)
    {genre_label}: [Value]
    ─────────────────
    {pitch_label}: [1-2 sentence synopsis in {target_lang}]
    """
    
    suggestion = await ask_llm(prompt) 
    clean_suggestion = suggestion.replace("*", "").strip()
    
    first_line = clean_suggestion.split('\n')[0].strip()
    if first_line and first_line not in history_titles:
        context.user_data['history_movie'].append({
            'timestamp': current_time,
            'title': first_line
        })
    
    keyboard = [[InlineKeyboardButton(btn_text, callback_data="reroll_movie")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await status_msg.edit_text(clean_suggestion, reply_markup=reply_markup)
        return clean_suggestion
    except Exception as e:
        logger.error(f"❌ Movie Display Error: {e}")
        err_msg = "⚠️ Échec de la suggestion." if lang == 'fr' else "⚠️ Movie suggestion failed."
        await status_msg.edit_text(err_msg)
        return None


async def music_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    
    lang = context.user_data.get('lang', 'fr')
    
    query = update.callback_query
    if query:
        await query.answer()
        logger.info(f"▶️ User {update.effective_chat.id} triggered re-roll for /music")
        keywords = context.user_data.get('last_music', 'chill acoustic')
    else:
        logger.info(f"▶️ User {update.effective_chat.id} triggered /music")
        keywords = " ".join(context.args)
        context.user_data['last_music'] = keywords

    if keywords and not query:
        kw_lower = keywords.lower()
        if any(w in kw_lower for w in ["musique", "chanson", "pour", "avec", "de", "détente", "sport", "ambiance", "playlist"]):
            lang = 'fr'
            context.user_data['lang'] = 'fr'
        elif any(w in kw_lower for w in ["music", "song", "for", "with", "chill", "workout", "vibe", "playlist"]):
            lang = 'en'
            context.user_data['lang'] = 'en'
        
    if not keywords:
        if lang == 'fr':
            usage_text = (
                "⚠️ <b>Utilisation :</b> /music [genre/ambiance/activité]\n"
                "<i>Exemples :</i>\n"
                "• <code>/music rock alternatif</code>\n"
                "• <code>/music playlist de musculation</code>"
            )
        else:
            usage_text = (
                "⚠️ <b>Usage:</b> /music [genre/vibe/activity]\n"
                "<i>Examples:</i>\n"
                "• <code>/music alternative rock</code>\n"
                "• <code>/music workout playlist</code>"
            )
        await update.message.reply_text(usage_text, parse_mode=ParseMode.HTML)
        return None

    safe_keywords = html.escape(keywords)
    status_text = f"🎧 <i>Recherche de '{safe_keywords}'...</i>" if lang == 'fr' else f"🎧 <i>Searching for '{safe_keywords}'...</i>"
    btn_text = "🔄 Autre idée" if lang == 'fr' else "🔄 Spin another track"
    
    if query:
        status_msg = await query.edit_message_text(status_text, parse_mode=ParseMode.HTML)
    else:
        status_msg = await update.effective_message.reply_text(status_text, parse_mode=ParseMode.HTML)
    
    current_time = time.time()
    one_week_in_seconds = 7 * 24 * 60 * 60
    if 'history_music' not in context.user_data: context.user_data['history_music'] = []
    
    valid_history = [item for item in context.user_data['history_music'] if (current_time - item['timestamp']) < one_week_in_seconds]
    context.user_data['history_music'] = valid_history
    history_titles = [item['title'] for item in valid_history]
    history_text = "\n".join(f"- {title}" for title in history_titles) if history_titles else "None."

    target_lang = "FRENCH" if lang == 'fr' else "ENGLISH"
    genre_label = "Genre"
    vibe_label = "Ambiance" if lang == 'fr' else "Vibe"

    prompt = f"""
    [ROLE]
    You are an elite DJ and Music Curator.

    [CONTEXT]
    User Request: "{keywords}"
    Recent Recommendations (Avoid these): {history_text}

    [TASK]
    Suggest EITHER a single masterpiece OR a curated mini-playlist (3-5 songs) based on the user's intent.
    - If the user explicitly asks for a "playlist", provide 5 iconic tracks.
    - Otherwise, suggest one perfect song or album.

    [STRICT INSTRUCTIONS]
    1. LANGUAGE OVERRIDE: Write natively in {target_lang}.
    2. PLAYLIST LOGIC: If providing a playlist, format each track as "♫ Title - Artist".
    3. SEMANTIC ACCURACY: For "white girl music", include high-energy pop anthems (Taylor Swift, Katy Perry, etc.).
    4. NO HALLUCINATIONS: REAL artists and songs only.
    5. FORMATTING: Plain text only. No Markdown (no asterisks). Exactly 2 or 3 emojis.

    [OUTPUT STRUCTURE]
    [♫ Title - Artist] or [♫ Playlist Name]
    {genre_label}: [Value]
    ─────────────────
    {vibe_label}: [1-2 sentence pitch in {target_lang}]
    [If Playlist: List the 5 tracks here]
    """
    
    suggestion = await ask_llm(prompt) 
    clean_suggestion = suggestion.replace("*", "").strip()
    
    first_line = clean_suggestion.split('\n')[0].strip()
    if first_line and first_line not in history_titles:
        context.user_data['history_music'].append({
            'timestamp': current_time,
            'title': first_line
        })
    
    keyboard = [[InlineKeyboardButton(btn_text, callback_data="reroll_music")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await status_msg.edit_text(clean_suggestion, reply_markup=reply_markup)
        return clean_suggestion
    except Exception as e:
        logger.error(f"❌ Music Display Error: {e}")
        err_msg = "⚠️ Échec de la suggestion musicale." if lang == 'fr' else "⚠️ Track suggestion failed."
        await status_msg.edit_text(err_msg)
        return None


async def book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    
    lang = context.user_data.get('lang', 'fr')
    query = update.callback_query
    if query:
        await query.answer()
        logger.info(f"▶️ User {update.effective_chat.id} triggered re-roll for /book")
        keywords = context.user_data.get('last_book', 'a cozy mystery')
    else:
        logger.info(f"▶️ User {update.effective_chat.id} triggered /book")
        keywords = " ".join(context.args)
        context.user_data['last_book'] = keywords

    if keywords and not query:
        kw_lower = keywords.lower()
        if any(w in kw_lower for w in ["livre", "roman", "pour", "avec", "de", "histoire", "auteur", "lire", "philosophie"]):
            lang = 'fr'
            context.user_data['lang'] = 'fr'
        elif any(w in kw_lower for w in ["book", "novel", "for", "with", "story", "author", "read", "philosophy"]):
            lang = 'en'
            context.user_data['lang'] = 'en'
        
    if not keywords:
        if lang == 'fr':
            usage_text = (
                "⚠️ <b>Utilisation :</b> /book [genre/ambiance/sujet]\n"
                "<i>Exemples :</i>\n"
                "• <code>/book de la science-fiction avec des thèmes philosophiques</code>\n"
                "• <code>/book roman policier haletant</code>"
            )
        else:
            usage_text = (
                "⚠️ <b>Usage:</b> /book [genre/vibe/topic]\n"
                "<i>Examples:</i>\n"
                "• <code>/book sci-fi with philosophical themes</code>\n"
                "• <code>/book a gripping thriller</code>"
            )
        await update.message.reply_text(usage_text, parse_mode=ParseMode.HTML)
        return None

    safe_keywords = html.escape(keywords)
    
    if lang == 'fr':
        status_text = f"📚 <i>Recherche de '{safe_keywords}'...</i>"
        btn_text = "🔄 Autre livre"
    else:
        status_text = f"📚 <i>Searching for '{safe_keywords}'...</i>"
        btn_text = "🔄 Turn the page"
    
    if query:
        status_msg = await query.edit_message_text(status_text, parse_mode=ParseMode.HTML)
    else:
        status_msg = await update.effective_message.reply_text(status_text, parse_mode=ParseMode.HTML)
    
    current_time = time.time()
    one_week_seconds = 7 * 24 * 60 * 60
    
    if 'history_book' not in context.user_data:
        context.user_data['history_book'] = []
        
    valid_history = [
        item for item in context.user_data['history_book'] 
        if (current_time - item['timestamp']) < one_week_seconds
    ]
    context.user_data['history_book'] = valid_history
    
    history_titles = [item['title'] for item in valid_history]
    history_text = "\n".join(f"- {t}" for t in history_titles) if history_titles else "None."

    target_lang = "FRENCH" if lang == 'fr' else "ENGLISH"
    genre_label = "Genre"
    pitch_label = "Synopsis" if lang == 'fr' else "Pitch"

    prompt = f"""
    [ROLE]
    You are an elite Literary Curator and Librarian.

    [CONTEXT]
    User Request: "{keywords}"

    [DO NOT RECOMMEND - RECENT SUGGESTIONS]
    You MUST NOT suggest any of the following books. They have already been recommended recently:
    {history_text}

    [TASK]
    Suggest ONE perfect, highly-acclaimed book (fiction or non-fiction) based on the TRUE MEANING of the request.

    [STRICT INSTRUCTIONS]
    1. LANGUAGE OVERRIDE: You MUST write the ENTIRE recommendation natively in {target_lang}. Do not drift into English if {target_lang} is FRENCH.
    2. SEMANTIC CURATION: Interpret the vibe and meaning of the request. If the user asks for a masterpiece, recommend something timeless. DO NOT just search for a book with the user's exact words in the title.
    3. NO HALLUCINATIONS: You must recommend a REAL, existing, published book by a REAL author. Do not invent titles or authors.
    4. CASING: Use normal **Sentence Case** for the {pitch_label}. Do NOT use Title Case for every word.
    5. FORMATTING: Plain text only. No Markdown (no asterisks). Do not use brackets [] for the labels.

    [OUTPUT STRUCTURE]
    📖 Title by Author (Year)
    {genre_label}: [Value]
    ─────────────────
    {pitch_label}: [1-2 sentence pitch in {target_lang}]
    """
    
    suggestion = await ask_llm(prompt) 
    clean_suggestion = suggestion.replace("*", "").strip()
    
    first_line = clean_suggestion.split('\n')[0].strip()
    if first_line and first_line not in history_titles:
        context.user_data['history_book'].append({
            'timestamp': current_time,
            'title': first_line
        })
    
    keyboard = [[InlineKeyboardButton(btn_text, callback_data="reroll_book")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await status_msg.edit_text(clean_suggestion, reply_markup=reply_markup)
        return clean_suggestion
    except Exception as e:
        logger.error(f"❌ Book Display Error: {e}")
        err_msg = "⚠️ Échec de la suggestion littéraire." if lang == 'fr' else "⚠️ Book suggestion failed."
        await status_msg.edit_text(err_msg)
        return None