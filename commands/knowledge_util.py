import re
import html
import asyncio
import logging
import requests
import datetime
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from modules.ai_core import ask_llm
from modules.utils import parse_time_string, is_authorized

logger = logging.getLogger(__name__)

# ==========================================
# KNOWLEDGE & UTILITY COMMANDS
# ==========================================
async def research_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    
    user_input = update.message.text if update.message and update.message.text else ""
    logger.info(f"▶️ User {update.effective_chat.id} triggered /research with: {user_input}")
    
    query = " ".join(context.args)
    lang = context.user_data.get('lang', 'fr')
    
    if user_input:
        input_lower = user_input.lower()
        if any(w in input_lower.split() for w in ["le", "la", "les", "des", "en", "france", "suisse", "pourquoi", "comment", "actu", "recherche", "qui", "quoi"]):
            lang = 'fr'
            context.user_data['lang'] = 'fr'
        elif any(w in input_lower.split() for w in ["research", "who", "what", "why", "how", "the", "a", "is", "of", "in"]):
            lang = 'en'
            context.user_data['lang'] = 'en'

    if not query:
        if lang == 'fr':
            usage = "⚠️ <b>Veuillez fournir un sujet !</b>\n<i>Exemple : /research neutralité suisse 2026</i>"
        else:
            usage = "⚠️ <b>Please provide a topic!</b>\n<i>Example: /research Swiss neutrality 2026</i>"
        await update.message.reply_text(usage, parse_mode=ParseMode.HTML)
        return None

    status_text = f"🔍 <i>Recherche sur '{html.escape(query)}'...</i>" if lang == 'fr' else f"🔍 <i>Researching '{html.escape(query)}'...</i>"
    status_msg = await update.message.reply_text(status_text, parse_mode=ParseMode.HTML)

    try:
        search_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        res = await asyncio.to_thread(requests.get, search_url, timeout=10)
        soup = BeautifulSoup(res.content, "xml")
        headlines = [item.title.text for item in soup.find_all("item", limit=5)]
        
        target_lang = "FRENCH" if lang == 'fr' else "ENGLISH"
        
        if headlines:
            source_material = f"Headlines:\n" + "\n".join(headlines)
            role = "Senior Intelligence Analyst specializing in OSINT"
            task = f"Provide a 3-sentence situation report on '{query}' based EXCLUSIVELY on the headlines provided."
        else:
            source_material = "No recent headlines found. Use general verified knowledge."
            role = "Highly accurate Research Librarian"
            task = f"Explain the core concept or historical facts of '{query}'."

        prompt = f"""
        [ROLE]
        You are a {role}.

        [CONTEXT]
        Topic: {query}
        {source_material}

        [TASK]
        {task}

        [STRICT INSTRUCTIONS]
        1. LANGUAGE OVERRIDE: You MUST write the ENTIRE report natively in {target_lang}. If the headlines are in English and the target language is FRENCH, translate the information before summarizing. Do not drift into English.
        2. FACTUAL ACCURACY: Do not hallucinate. If info is missing, state it clearly in {target_lang}.
        3. CASING: Use normal **Sentence Case**. Do NOT use Title Case for every word. No ALL CAPS headers.
        4. FORMATTING: Plain text only. No Markdown (no asterisks).
        5. STRUCTURE: Exactly 3 concise sentences. No preamble.
        """
        
        analysis = await ask_llm(prompt)
        clean_analysis = analysis.replace("*", "").strip()
        header_text = "Recherche" if lang == 'fr' else "Research"
        
        final_text = f"📝 <b>{header_text} : {html.escape(query.title())}</b>\n─────────────────\n{clean_analysis}"
        await status_msg.edit_text(final_text, parse_mode=ParseMode.HTML)
        return clean_analysis
        
    except Exception as e:
        logger.error(f"❌ Research error: {e}")
        error_msg = f"⚠️ La recherche a échoué : {str(e)}" if lang == 'fr' else f"⚠️ Research failed: {str(e)}"
        await status_msg.edit_text(error_msg)
        return None


async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    
    user_input = update.message.text if update.message and update.message.text else ""
    logger.info(f"▶️ User {update.effective_chat.id} triggered /weather with: {user_input}")
    
    lang = context.user_data.get('lang', 'fr')
    
    if user_input:
        input_lower = user_input.lower()
        if any(w in input_lower.split() for w in ["météo", "meteo", "temps", "fait", "chaud", "froid"]):
            lang = 'fr'
            context.user_data['lang'] = 'fr'
        elif any(w in input_lower.split() for w in ["weather", "forecast", "hot", "cold", "rain"]):
            lang = 'en'
            context.user_data['lang'] = 'en'
    
    raw_args = " ".join(context.args).lower()
    target_day = 0
    time_context = "Current"
    
    days_match = re.search(r'(in|dans)\s*(\d+)\s*(days|jours|jour|day)', raw_args)
    if days_match:
        requested_days = int(days_match.group(2))
        target_day = min(requested_days, 2)
        time_context = "Day after tomorrow" if target_day == 2 else ("Tomorrow" if target_day == 1 else "Today")
        raw_args = raw_args.replace(days_match.group(0), "")
    else:
        time_phrases = {
            2: ["après demain", "apres demain", "après-demain", "apres-demain", "day after tomorrow"],
            1: ["demain", "tomorrow"],
            0: ["aujourd'hui", "today", "maintenant", "now"]
        }
        for day_index, phrases in time_phrases.items():
            for phrase in phrases:
                if phrase in raw_args:
                    target_day = day_index
                    time_context = ["Today", "Tomorrow", "Day after tomorrow"][day_index]
                    raw_args = raw_args.replace(phrase, "")
                    break 

    fluff_words = [
        "quel", "temps", "fera", "t-il", "t", "il", "à", "a", "in", "for", "pour", "le", "la", "the", "on", "de",
        "what", "whats", "what's", "is", "weather", "météo", "meteo", "forecast", "how", "like"
    ]
    clean_words = [w for w in raw_args.split() if w not in fluff_words]
    city_query = " ".join(clean_words).strip()
    
    if not city_query:
        city_query = "Lausanne"
        
    display_name = city_query.title()
    safe_display = html.escape(display_name)
    
    if lang == 'fr':
        status_text = f"<i>Recherche de la météo pour {safe_display}...</i> 🌍"
        header_text = f"Météo : {safe_display}"
        err_not_found = f"⚠️ <i>Impossible de trouver les données météo pour '<b>{safe_display}</b>'.</i>"
    else:
        status_text = f"<i>Looking up the weather for {safe_display}...</i> 🌍"
        header_text = f"Forecast: {safe_display}"
        err_not_found = f"⚠️ <i>I couldn't find weather data for '<b>{safe_display}</b>'.</i>"
    
    status_msg = await update.message.reply_text(status_text, parse_mode=ParseMode.HTML)
    
    weather_url = f"https://wttr.in/{city_query}?format=j1"
    headers = {"User-Agent": "MattouBot/1.0 (Telegram Assistant)"}
    
    try:
        res = await asyncio.to_thread(requests.get, weather_url, headers=headers, timeout=10)
        if res.status_code != 200:
            await status_msg.edit_text(err_not_found, parse_mode=ParseMode.HTML)
            return None
            
        data = res.json()
        
        if target_day == 0:
            current = data['current_condition'][0]
            temp_str = f"Current Temp: {current['temp_C']}°C"
            condition = current['weatherDesc'][0]['value']
        else:
            forecast_data = data['weather'][target_day]
            temp_max = forecast_data['maxtempC']
            temp_min = forecast_data['mintempC']
            cond_morning = forecast_data['hourly'][3]['weatherDesc'][0]['value']
            cond_afternoon = forecast_data['hourly'][5]['weatherDesc'][0]['value']
            
            temp_str = f"Lowest: {temp_min}°C, Highest: {temp_max}°C"
            if cond_morning == cond_afternoon:
                condition = cond_afternoon
            else:
                condition = f"Morning: {cond_morning}, Afternoon: {cond_afternoon}"
        
        target_lang = "FRENCH" if lang == 'fr' else "ENGLISH"
        
        prompt = f"""
        [ROLE]
        You are a witty, slightly sassy, and caring virtual assistant.

        [CONTEXT]
        Location: {display_name}
        Target Time: {time_context}
        Temperatures: {temp_str}
        Sky Conditions: {condition}

        [TASK]
        Write a short, high-personality weather report based on the "Target Time" and "Temperatures". Tell them how it will feel and give a specific outfit/activity recommendation.

        [STRICT INSTRUCTIONS]
        1. LANGUAGE OVERRIDE: You MUST write the ENTIRE response natively in {target_lang}. CRITICAL: You must explicitly translate English sky conditions (like 'partly cloudy', 'overcast') into natural {target_lang}.
        2. STRUCTURE: Exactly 2 sentences. No intros.
        3. DATA USAGE: If a High and Low temperature are provided, you MUST explicitly mention BOTH in your report, ordering from lowest to highest (e.g., "allant de 9°C à 21°C").
        4. TEMPORAL ACCURACY: If the Target Time is tomorrow or later, use future tense (e.g., "Il fera...").
        5. CASING: Use normal **Sentence Case** only. Do not use Title Case for every word.
        6. FORMATTING: Plain text ONLY. No Markdown. 
        7. EMOJIS: Include exactly 2 emojis at the very end.

        [OUTPUT STRUCTURE]
        [Sentence 1]. [Sentence 2] [Emoji][Emoji]
        """

        forecast = await ask_llm(prompt, max_tokens=200)
        clean_forecast = forecast.replace("*", "").strip()
        
        time_indicator = f" ({time_context})" if target_day > 0 else ""
        if lang == 'fr' and target_day == 1: time_indicator = " (Demain)"
        if lang == 'fr' and target_day == 2: time_indicator = " (Après-demain)"
        
        final_text = f"🌍 <b>{header_text}{time_indicator}</b>\n─────────────────\n{clean_forecast}" 
        await status_msg.edit_text(final_text, parse_mode=ParseMode.HTML)
        
        return f"Weather in {display_name} ({time_context}): {clean_forecast}"
        
    except Exception as e:
        logger.error(f"❌ Weather Command Error: {e}")
        err_general = f"⚠️ Données météo indisponibles : {str(e)}" if lang == 'fr' else f"⚠️ Weather data unavailable: {str(e)}"
        await status_msg.edit_text(err_general)
        return None


async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    logger.info(f"▶️ User {update.effective_chat.id} triggered /remind")
    chat_id = update.effective_chat.id
    
    user_input = update.message.text if update.message and update.message.text else ""
    lang = context.user_data.get('lang', 'fr')
    
    if user_input:
        input_lower = user_input.lower()
        if any(w in input_lower for w in ["rappel", "rappelle", "dans", "chrono"]):
            lang = 'fr'
            context.user_data['lang'] = 'fr'
        elif any(w in input_lower for w in ["remind", "timer", "in", "alarm"]):
            lang = 'en'
            context.user_data['lang'] = 'en'

    try:
        if not context.args:
            raise ValueError("No arguments provided")

        time_input = context.args[0]
        message = " ".join(context.args[1:]).strip()
        total_seconds = parse_time_string(time_input)
        
        if total_seconds <= 0:
            raise ValueError("Invalid time")
            
        if not message:
            message = "Fin du chrono !" if lang == 'fr' else "Timer finished!"
            is_generic = True
        else:
            is_generic = False

        job_data = {"message": message, "lang": lang}
        context.job_queue.run_once(remind_callback, total_seconds, data=job_data, chat_id=chat_id)
        
        if total_seconds < 60:
            time_display = f"{total_seconds} secondes" if lang == 'fr' else f"{total_seconds} seconds"
        else:
            mins = total_seconds // 60
            if mins < 60:
                time_display = f"{mins} minute{'s' if mins > 1 else ''}"
            else:
                hrs = mins // 60
                time_display = f"{hrs} heure{'s' if hrs > 1 else ''}" if lang == 'fr' else f"{hrs} hour{'s' if hrs > 1 else ''}"
        
        if lang == 'fr':
            header = "Rappel programmé"
            if is_generic:
                display_text = f"🕒 C'est noté ! Je vous enverrai un rappel dans {time_display}."
            else:
                display_text = f"🕒 C'est noté ! Je vous rappellerai de <b>{html.escape(message)}</b> dans {time_display}."
        else:
            header = "Reminder set"
            if is_generic:
                display_text = f"🕒 Got it! I'll send you a reminder in {time_display}."
            else:
                display_text = f"🕒 Got it! I will remind you to <b>{html.escape(message)}</b> in {time_display}."
            
        final_ui = f"🕒 <b>{header}</b>\n─────────────────\n{display_text}"
        await update.message.reply_text(final_ui, parse_mode=ParseMode.HTML)
        return f"Reminder set for {time_display}"

    except (IndexError, ValueError):
        if lang == 'fr':
            usage = "⚠️ <b>Utilisation :</b> /remind [temps] [message]\n<i>Exemple : /remind 10m sortir les pâtes</i>"
        else:
            usage = "⚠️ <b>Usage:</b> /remind [time] [message]\n<i>Example: /remind 10m check the pasta</i>"
            
        await update.message.reply_text(usage, parse_mode=ParseMode.HTML)
        return None


async def remind_callback(context: ContextTypes.DEFAULT_TYPE):
    """The job that executes when the timer expires."""
    job = context.job
    job_data = job.data if isinstance(job.data, dict) else {"message": str(job.data), "lang": "en"}
    message = job_data.get("message", "Timer finished!")
    lang = job_data.get("lang", "en")
    label = "RAPPEL" if lang == 'fr' else "REMINDER"
    await context.bot.send_message(
        chat_id=job.chat_id, 
        text=f"🔔 <b>{label} :</b> {html.escape(message)}", 
        parse_mode=ParseMode.HTML
    )


async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    
    user_input = update.message.text if update.message and update.message.text else "What time is it?"
    logger.info(f"▶️ User {update.effective_chat.id} triggered /time with: {user_input}")
    
    lang = context.user_data.get('lang', 'fr')
    
    if user_input:
        input_lower = user_input.lower()
        if any(w in input_lower.split() for w in ["heure", "date", "maintenant", "temps"]):
            lang = 'fr'
            context.user_data['lang'] = 'fr'
        elif any(w in input_lower.split() for w in ["time", "clock", "date", "today"]):
            lang = 'en'
            context.user_data['lang'] = 'en'
            
    status_text = "🕒 <i>Mattou regarde sa montre...</i>" if lang == 'fr' else "🕒 <i>Mattou checks its clock...</i>"
    status_msg = await update.message.reply_text(status_text, parse_mode=ParseMode.HTML)
    
    try:
        tz = ZoneInfo("Europe/Zurich")
        current_time_str = datetime.datetime.now(tz).strftime("%A, %B %d, %Y - %H:%M")
    except Exception:
        current_time_str = datetime.datetime.now().strftime("%A, %B %d, %Y - %H:%M")
    
    target_lang = "FRENCH" if lang == 'fr' else "ENGLISH"
    
    prompt = f"""
    [ROLE]
    You are MattouBot, a witty and helpful personal assistant.

    [CONTEXT]
    User Request: "{user_input}"
    Real Current Time: {current_time_str}

    [TASK]
    Tell the user the exact time and date in a friendly, conversational way based on the "Real Current Time" provided.

    [STRICT INSTRUCTIONS]
    1. LANGUAGE OVERRIDE: You MUST write the ENTIRE response natively in {target_lang}. Translate the day, month, and time formatting (e.g., 14h30 instead of 2:30 PM if French). Do not drift into English if {target_lang} is FRENCH.
    2. STRUCTURE: 1 or 2 short sentences. No preamble.
    3. CASING: Use normal **Sentence Case**.
    4. FORMATTING: Plain text ONLY. No Markdown (no asterisks). 
    5. EMOJIS: Include exactly 1 or 2 relevant emojis.

    [OUTPUT STRUCTURE]
    [Your friendly response stating the time] [Emoji]
    """
    
    try:
        time_output = await ask_llm(prompt)
        clean_time = time_output.replace("*", "").strip()
        
        await status_msg.edit_text(clean_time)
        return clean_time
        
    except Exception as e:
        logger.error(f"❌ Time Command Error: {e}")
        fallback_time = f"🕒 Il est {current_time_str}." if lang == 'fr' else f"🕒 It is {current_time_str}."
        await status_msg.edit_text(fallback_time)
        return fallback_time