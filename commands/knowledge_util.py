import html
import asyncio
import logging
import requests
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
    logger.info(f"▶️ User {update.effective_chat.id} triggered /research")
    
    query = " ".join(context.args)
    lang = context.user_data.get('lang', 'fr')
    
    if query:
        query_lower = query.lower()
        if any(w in query_lower.split() for w in ["le", "la", "les", "des", "en", "france", "suisse", "pourquoi", "comment", "actu"]):
            lang = 'fr'
            context.user_data['lang'] = 'fr'

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
        
        final_text = f"📝 <b>{header_text} : {html.escape(query.title())}</b>\n──────────────────────\n{clean_analysis}"
        await status_msg.edit_text(final_text, parse_mode=ParseMode.HTML)
        return clean_analysis
        
    except Exception as e:
        logger.error(f"❌ Research error: {e}")
        error_msg = f"⚠️ La recherche a échoué : {str(e)}" if lang == 'fr' else f"⚠️ Research failed: {str(e)}"
        await status_msg.edit_text(error_msg)
        return None


async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    logger.info(f"▶️ User {update.effective_chat.id} triggered /weather")
    
    city_query = " ".join(context.args) or "Lausanne"
    display_name = city_query.title()
    
    status_msg = await update.message.reply_text(f"<i>Looking up the weather for {html.escape(display_name)}...</i> 🌍", parse_mode=ParseMode.HTML)
    
    weather_url = f"https://wttr.in/{city_query}?format=j1"
    headers = {"User-Agent": "MattouBot/1.0 (Telegram Assistant)"}
    
    try:
        res = await asyncio.to_thread(requests.get, weather_url, headers=headers, timeout=10)
        if res.status_code != 200:
            await status_msg.edit_text(f"⚠️ <i>I couldn't find weather data for '<b>{html.escape(display_name)}</b>'.</i>", parse_mode=ParseMode.HTML)
            return None
            
        data = res.json()
        current = data['current_condition'][0]
        temp = current['temp_C']
        condition = current['weatherDesc'][0]['value']
        
        prompt = f"""
        [ROLE]
        You are a witty, slightly sassy, and caring virtual assistant.

        [CONTEXT]
        User Request: "{city_query}"
        Location: {display_name}
        Current Temperature: {temp}°C
        Sky Conditions: {condition}

        [LANGUAGE ANCHORING - CRITICAL]
        Examine the "User Request" above to detect the language.
        You MUST begin your response by explicitly declaring that language using exactly one of these tags: [LANG: EN] or [LANG: FR].
        If ambiguous, default to French.
        After outputting the tag, write the ENTIRE rest of the response in that chosen language.

        [TASK]
        Write a short, high-personality weather report. Tell them how it feels and give a specific outfit/activity recommendation.

        [STRICT INSTRUCTIONS]
        1. STRUCTURE: Exactly 2 sentences. No intros.
        2. CASING & PUNCTUATION: Use normal **Sentence Case** only (capitalize the first word of the sentence and proper nouns like city names). 
           STRICTLY FORBIDDEN: Do not use Title Case for every word (e.g., do NOT write "The Weather Is Good").
        3. FORMATTING: Plain text ONLY. No Markdown (no asterisks). 
        4. EMOJIS: Include exactly 2 emojis at the very end.

        [OUTPUT STRUCTURE]
        [LANG: XX]
        [Sentence 1]. [Sentence 2] [Emoji][Emoji]
        """

        forecast = await ask_llm(prompt, max_tokens=200)
        clean_forecast = forecast.replace("[LANG: FR]", "").replace("[LANG: EN]", "").replace("*", "").strip()
        
        final_text = f"🌍 <b>Forecast: {html.escape(display_name)}</b>\n──────────────────────\n{clean_forecast}" 
        await status_msg.edit_text(final_text, parse_mode=ParseMode.HTML)
        return f"Weather in {display_name}: {clean_forecast}"
        
    except Exception as e:
        logger.error(f"❌ Weather Command Error: {e}")
        await status_msg.edit_text(f"⚠️ Weather data unavailable: {str(e)}")
        return None


async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    logger.info(f"▶️ User {update.effective_chat.id} triggered /remind")
    chat_id = update.effective_chat.id
    lang = context.user_data.get('lang', 'en')
    try:
        time_input = context.args[0]
        message = " ".join(context.args[1:])
        total_seconds = parse_time_string(time_input)
        
        if total_seconds <= 0 or not message:
            raise ValueError("Invalid input")
            
        job_data = {"message": message, "lang": lang}
        context.job_queue.run_once(remind_callback, total_seconds, data=job_data, chat_id=chat_id)
        
        if total_seconds < 60:
            time_display = f"{total_seconds} seconds" if lang == 'en' else f"{total_seconds} secondes"
        else:
            mins = total_seconds // 60
            if mins < 60:
                time_display = f"{mins} minutes"
            else:
                hrs = mins // 60
                time_display = f"{hrs} hour(s)" if lang == 'en' else f"{hrs} heure(s)"
        
        if lang == 'fr':
            confirmation = f"🕒 Rappel programmé : je vous rappellerai de '{message}' dans {time_display}."
            display_text = f"🕒 C'est noté ! Je vous rappellerai de <b>{html.escape(message)}</b> dans {time_display}."
        else:
            confirmation = f"🕒 Reminder set: I will remind you to '{message}' in {time_display}."
            display_text = f"🕒 Got it! I will remind you to <b>{html.escape(message)}</b> in {time_display}."
            
        await update.message.reply_text(display_text, parse_mode=ParseMode.HTML)
        return confirmation

    except (IndexError, ValueError):
        if lang == 'fr':
            usage = "⚠️ <b>Utilisation :</b> /remind [temps] [message]\n<i>Exemple : /remind 10m sortir les pâtes</i>"
        else:
            usage = "⚠️ <b>Usage:</b> /remind [time] [message]\n<i>Example: /remind 10m check the pasta</i>"
            
        await update.message.reply_text(usage, parse_mode=ParseMode.HTML)
        return None


async def remind_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    job_data = job.data if isinstance(job.data, dict) else {"message": job.data, "lang": "en"}
    message = job_data.get("message", "")
    lang = job_data.get("lang", "en")
    label = "RAPPEL" if lang == 'fr' else "REMINDER"
    await context.bot.send_message(
        chat_id=job.chat_id, 
        text=f"🔔 <b>{label}:</b> {html.escape(message)}", 
        parse_mode=ParseMode.HTML
    )