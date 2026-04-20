import html
import asyncio
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from modules.ai_core import ask_llm
from modules.utils import get_lang_rule, parse_time_string, is_authorized

logger = logging.getLogger(__name__)

# ==========================================
# KNOWLEDGE & UTILITY COMMANDS
# ==========================================
async def research_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    logger.info(f"▶️ User {update.effective_chat.id} triggered /research")
    
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("⚠️ <b>Please provide a topic!</b>\n<i>Example: /research Swiss neutrality 2026</i>", parse_mode=ParseMode.HTML)
        return None

    status_msg = await update.message.reply_text(f"🔍 <i>Researching '{html.escape(query)}'...</i>", parse_mode=ParseMode.HTML)

    try:
        search_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        res = await asyncio.to_thread(requests.get, search_url, timeout=10)
        soup = BeautifulSoup(res.content, "xml")
        headlines = [item.title.text for item in soup.find_all("item", limit=5)]
        
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
        
        [LANGUAGE ANCHORING - CRITICAL]
        You MUST begin your response by explicitly declaring the detected language of the User Request using exactly one of these tags: [LANG: EN] or [LANG: FR].
        If ambiguous, default to French.
        After outputting the tag, write the ENTIRE rest of the response in that chosen language.

        [TASK]
        {task}

        [STRICT INSTRUCTIONS]
        1. FACTUAL ACCURACY: Do not hallucinate. If info is missing, state it clearly.
        2. FORMATTING: Use Normal Sentence Case. No ALL CAPS headers. No Markdown (no asterisks).
        3. STRUCTURE: Exactly 3 concise sentences. No preamble.
        """
        
        analysis = await ask_llm(prompt)
        clean_analysis = analysis.replace("[LANG: FR]", "").replace("[LANG: EN]", "").replace("*", "").strip()
        
        final_text = f"📝 <b>Research: {html.escape(query.title())}</b>\n──────────────────────\n{clean_analysis}"
        await status_msg.edit_text(final_text, parse_mode=ParseMode.HTML)
        return clean_analysis
        
    except Exception as e:
        logger.error(f"❌ Research error: {e}")
        await status_msg.edit_text(f"⚠️ Research failed: {str(e)}")
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
        Location: {display_name}
        Current Temperature: {temp}°C
        Sky Conditions: {condition}

        [LANGUAGE ANCHORING - CRITICAL]
        You MUST begin your response by explicitly declaring the detected language of the User Request using exactly one of these tags: [LANG: EN] or [LANG: FR].
        If ambiguous, default to French.
        After outputting the tag, write the ENTIRE rest of the response in that chosen language.

        [TASK]
        Write a short, high-personality weather report. Tell them how it feels and give a specific outfit/activity recommendation.

        [STRICT INSTRUCTIONS]
        1. STRUCTURE: Exactly 2 sentences. No intros.
        2. FORMATTING: Plain text ONLY. No Markdown (no asterisks). Use Title Case for the city name.
        3. EMOJIS: Include exactly 2 emojis at the very end.
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
    
    try:
        time_input = context.args[0]
        message = " ".join(context.args[1:])
        total_seconds = parse_time_string(time_input)
        
        if total_seconds <= 0 or not message:
            raise ValueError("Invalid input")
            
        context.job_queue.run_once(remind_callback, total_seconds, data=message, chat_id=chat_id)
        
        if total_seconds < 60:
            time_display = f"{total_seconds} seconds"
        else:
            mins = total_seconds // 60
            time_display = f"{mins} minutes" if mins < 60 else f"{mins//60} hour(s)"
        
        confirmation = f"🕒 Reminder set: I will remind you to '{message}' in {time_display}."
        await update.message.reply_text(f"🕒 Got it! I will remind you to <b>{html.escape(message)}</b> in {time_display}.", parse_mode=ParseMode.HTML)
        return confirmation

    except (IndexError, ValueError):
        usage = "⚠️ <b>Usage:</b> /remind [time] [message]\n<i>Example: /remind 10m check the pasta</i>"
        await update.message.reply_text(usage, parse_mode=ParseMode.HTML)
        return None

async def remind_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        chat_id=job.chat_id, 
        text=f"🔔 <b>REMINDER:</b> {html.escape(job.data)}", 
        parse_mode=ParseMode.HTML
    )