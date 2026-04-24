import html
import asyncio
import logging
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from modules.ai_core import ask_llm
from modules.config import PORTFOLIO_MAP
from modules.utils import is_authorized 

logger = logging.getLogger(__name__)

# ==========================================
# FINANCE & NEWS COMMANDS
# ==========================================
async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches live market data and returns a summary for global memory."""
    if not is_authorized(update): return None
    logger.info(f"▶️ User {update.effective_chat.id} triggered /portfolio")
    
    status_msg = await update.message.reply_text("📈 <i>Fetching live market data...</i>", parse_mode=ParseMode.HTML)
    stats = []
    
    for ticker, name in PORTFOLIO_MAP.items():
        try:
            safe_name = html.escape(name)
            stock = yf.Ticker(ticker)
            data = await asyncio.to_thread(stock.history, period="5d")
            
            if not data.empty and len(data) >= 2:
                current = data['Close'].iloc[-1]
                prev = data['Close'].iloc[-2]
                pct = ((current - prev) / prev) * 100
                
                indicator = "🟢" if pct >= 0 else "🔴"
                stats.append(f"• <b>{safe_name}</b>:\n  <code>{indicator} {current:.2f} ({pct:+.2f}%)</code>")
            else:
                stats.append(f"• <b>{safe_name}</b>:\n  <code>⚠️ Market closed</code>")
        except Exception as e:
            logger.error(f"❌ Portfolio Error for {ticker}: {e}")
            stats.append(f"• <b>{html.escape(name)}</b>:\n  <code>⚠️ Fetch failed</code>")
    
    header = "📊 <b>Live Market Portfolio</b>\n─────────────────\n"
    body = "\n".join(stats)
    full_response = f"{header}{body}"
    
    await status_msg.edit_text(full_response, parse_mode=ParseMode.HTML)
    return f"Portfolio Status: {', '.join([s.split('</b>')[0].replace('• <b>', '') for s in stats[:3]])}..."


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Synthesizes news and returns the executive summary for memory."""
    if not is_authorized(update): return None
    
    user_input = update.message.text if update.message and update.message.text else "News"
    logger.info(f"▶️ User {update.effective_chat.id} triggered /news with: {user_input}")
    
    lang = context.user_data.get('lang', 'fr')
    user_input_lower = user_input.lower()
    
    if any(w in user_input_lower for w in ["actu", "info", "bilan", "recherche", "nouvelle"]):
        lang = 'fr'
        context.user_data['lang'] = 'fr'
    elif any(w in user_input_lower for w in ["news", "briefing"]):
        lang = 'en'
        context.user_data['lang'] = 'en'

    status_text = "<i>Analyse de l'actualité...</i> ⏳" if lang == 'fr' else "<i>Analyzing headlines...</i> ⏳"
    status_msg = await update.message.reply_text(status_text, parse_mode=ParseMode.HTML)
    
    raw_news = []
    topic = " ".join(context.args).strip() if context.args else ""
    
    if topic:
        queries = [f"{topic} geopolitics", f"{topic} news"]
    else:
        queries = ["geopolitics world", "geopolitics Switzerland", "geopolitics France"]
    
    try:
        for q in queries:
            url = f"https://news.google.com/rss/search?q={q}+when:1d&hl=en-US&gl=US&ceid=US:en"
            res = await asyncio.to_thread(requests.get, url, timeout=10)
            soup = BeautifulSoup(res.content, "xml")
            for item in soup.find_all("item", limit=3 if topic else 2):
                raw_news.append(item.title.text)
        
        news_context = "\n".join(raw_news) if raw_news else "No recent headlines found."
        
        target_lang = "FRENCH" if lang == 'fr' else "ENGLISH"
        
        prompt = f"""
        [ROLE]
        You are a highly analytical Geopolitical Briefing Officer.

        [CONTEXT]
        User Request: "{user_input}"
        Raw headlines from the last 24h:
        {news_context}

        [TASK]
        Synthesize the headlines into a single, natural, and cohesive paragraph connecting the dots between events.
        CRITICAL: Ensure your briefing focuses primarily on answering the "User Request" (e.g., if they asked about France, focus heavily on the French headlines).

        [STRICT INSTRUCTIONS]
        1. LANGUAGE OVERRIDE: You MUST write the ENTIRE briefing natively in {target_lang}. Translate the English headlines into {target_lang} before summarizing. Do NOT drift into English if {target_lang} is FRENCH.
        2. OBJECTIVITY: Neutral, journalistic tone.
        3. NO HALLUCINATION: Only use the provided headlines.
        4. CASING: Use normal **Sentence Case** only. Capitalize the first word of sentences and proper nouns (i.e. France, or Lufthansa). Do NOT use Title Case for every word.
        5. FORMATTING: Plain text only. No Markdown (no asterisks).
        6. EMOJIS: Include exactly 2 relevant emojis at the end.

        [OUTPUT STRUCTURE]
        [Briefing paragraph of 4-6 sentences] [Emoji][Emoji]
        """
        
        summary = await ask_llm(prompt)
        clean_summary = summary.replace("*", "").strip()
        
        if topic:
            header_text = f"Actualité : {topic.title()}" if lang == 'fr' else f"News: {topic.title()}"
        else:
            header_text = "Bilan Géopolitique" if lang == 'fr' else "Geopolitical Briefing"
        
        final_text = f"📰 <b>{html.escape(header_text)}</b>\n─────────────────\n{clean_summary}"
        await status_msg.edit_text(final_text, parse_mode=ParseMode.HTML)
        return clean_summary

    except Exception as e:
        logger.error(f"❌ News Error: {e}")
        error_msg = "⚠️ Impossible de générer le résumé." if lang == 'fr' else "⚠️ News summary failed."
        await status_msg.edit_text(error_msg)
        return None