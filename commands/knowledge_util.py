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
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /research")
    
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("⚠️ <b>Please provide a topic!</b>\n<i>Example: /research Swiss neutrality 2026</i>", parse_mode=ParseMode.HTML)
        return

    status_msg = await update.message.reply_text(f"🔍 <i>Researching '{html.escape(query)}'...</i>", parse_mode=ParseMode.HTML)

    try:
        search_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        res = await asyncio.to_thread(requests.get, search_url, timeout=10)
        soup = BeautifulSoup(res.content, "xml")
        headlines = [item.title.text for item in soup.find_all("item", limit=5)]
        
        if headlines:
            headlines_text = "\n".join(headlines)
            prompt = f"""
            [ROLE]
            You are a senior Intelligence Analyst specializing in OSINT. Your standard is absolute factual accuracy.

            [SOURCE MATERIAL]
            Topic: {query}
            Headlines:
            {headlines_text}
            
            [TASK]
            Provide a 3-sentence situation report on '{query}' based EXCLUSIVELY on the headlines.

            [STRICT INSTRUCTIONS]
            1. STRICT SOURCE ADHERENCE: Do NOT use internal training data to add facts not found in the headlines.
            2. RELEVANCE CHECK: If the headlines lack specific information on '{query}', reply EXACTLY with: 
               "⚠️ The recent news headlines do not contain enough relevant information to provide a reliable summary."
            3. PLAIN TEXT ONLY: Absolutely NO HTML tags.
            4. NO MARKDOWN: Absolutely NO asterisks (*) or hashtags (#).

            [OUTPUT STRUCTURE]
            Exactly three sentences. No preamble.
            """
        else:
            prompt = f"""
            [ROLE]
            You are a highly accurate Research Librarian.

            [TASK]
            Explain the core concept or historical facts of '{query}'.

            [STRICT INSTRUCTIONS]
            1. FACTUAL GROUNDING: Rely only on verified, objective information.
            2. UNCERTAINTY PROTOCOL: If you do not have definitive knowledge, reply EXACTLY with:
               "⚠️ I do not have enough verified, reliable information to summarize this topic accurately."
            3. PLAIN TEXT ONLY: Absolutely NO HTML tags.
            4. NO MARKDOWN: Absolutely NO asterisks (*) or hashtags (#).

            [OUTPUT STRUCTURE]
            A concise 3-sentence summary. No preamble.
            """
            
        prompt += get_lang_rule(context)
        analysis = await ask_llm(prompt)
        safe_analysis = html.escape(analysis.replace('*', ''))
        safe_query = html.escape(query)
        await status_msg.edit_text(f"📝 <b>Research Summary: {safe_query}</b>\n\n{safe_analysis}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Research error: {e}")
        await status_msg.edit_text(f"⚠️ Research failed: {str(e)}")

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /weather")
    
    city_query = " ".join(context.args) or "Lausanne"
    display_name = html.escape(city_query.title())
    
    status_msg = await update.message.reply_text(f"<i>Looking up the weather for {display_name}...</i> 🌍", parse_mode=ParseMode.HTML)
    
    weather_url = f"https://wttr.in/{city_query}?format=j1"
    headers = {"User-Agent": "MattouBot/1.0 (Telegram Assistant)"}
    
    try:
        res = await asyncio.to_thread(requests.get, weather_url, headers=headers, timeout=10)
        
        if res.status_code != 200:
            await status_msg.edit_text(f"⚠️ <i>I couldn't find weather data for '<b>{display_name}</b>'. Did you make a typo?</i>", parse_mode=ParseMode.HTML)
            return
            
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
        If ambiguous (like a city name alone), default to French.
        After outputting the tag, write the ENTIRE rest of the response in that chosen language.

        [TASK]
        Write a short, high-personality weather report. Tell them how it feels and give a specific outfit/activity recommendation.

        [STRICT INSTRUCTIONS]
        1. STRUCTURE: Exactly 2 sentences. No intros, no "Sure!", just start.
        2. TONE: Cute, sassy, and practical.
        3. NO META-COMMENTARY: Absolutely NO notes, NO explanations, NO self-corrections, and NO "Corrected Version:".
        4. DATA-DRIVEN: 
           - If < 10°C: Recommend layers/warmth.
           - If > 25°C: Recommend hydration/light clothes.
           - If rain/clouds: Recommend umbrella/coziness.
        5. FORMATTING: Plain text ONLY. No Markdown (no asterisks).
        6. EMOJIS: Include exactly 2 emojis at the very end of the text.

        [OUTPUT STRUCTURE]
        [LANG: XX]
        [Sentence 1 about the weather]. [Sentence 2 with sassy recommendation] [Emoji 1][Emoji 2]
        """

        forecast = await ask_llm(prompt, max_tokens=200)
        clean_forecast = forecast.replace("[LANG: FR]", "").replace("[LANG: EN]", "").replace("*", "").strip()
        safe_forecast = html.escape(clean_forecast)
        
        await status_msg.edit_text(f"🌍 <b>Forecast for {display_name}</b>\n\n{safe_forecast}", parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"❌ Weather Command Error: {e}")
        await status_msg.edit_text(f"⚠️ Weather data unavailable: {str(e)}")

async def remind_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    safe_message = html.escape(job.data)
    await context.bot.send_message(
        chat_id=job.chat_id, 
        text=f"🔔 <b>REMINDER:</b> {safe_message}", 
        parse_mode=ParseMode.HTML
    )

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /remind")
    chat_id = update.effective_chat.id
    
    try:
        time_input = context.args[0]
        message = " ".join(context.args[1:])
        total_seconds = parse_time_string(time_input)
        
        if total_seconds <= 0:
            await update.message.reply_text("⚠️ <i>Time must be greater than 0.</i>", parse_mode=ParseMode.HTML)
            return
        if not message:
            await update.message.reply_text("⚠️ <i>What do you want me to remind you about?</i>", parse_mode=ParseMode.HTML)
            return
            
        context.job_queue.run_once(remind_callback, total_seconds, data=message, chat_id=chat_id)
        
        if total_seconds < 60:
            time_display = f"{total_seconds} second(s)"
        else:
            mins = total_seconds // 60
            hrs = mins // 60
            leftover_mins = mins % 60
            if hrs > 0:
                time_display = f"{hrs} hour(s)" + (f" and {leftover_mins} minute(s)" if leftover_mins else "")
            else:
                time_display = f"{mins} minute(s)"
        
        safe_message = html.escape(message)
        await update.message.reply_text(f"🕒 Got it! I will remind you to <b>{safe_message}</b> in {time_display}.", parse_mode=ParseMode.HTML)
    except (IndexError, ValueError) as e:
        error_msg = (
            "⚠️ <b>Usage:</b> /remind [time] [message]\n\n"
            "<i>Examples:</i>\n"
            "• <code>/remind 10 flip laundry</code> (10 mins)\n"
            "• <code>/remind 1h30 check the oven</code>\n"
            "• <code>/remind 45s take a breath</code>"
        )
        await update.message.reply_text(error_msg, parse_mode=ParseMode.HTML)