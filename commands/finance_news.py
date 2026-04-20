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
from modules.utils import get_lang_rule, is_authorized 

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
    
    header = "📊 <b>Live Market Portfolio</b>\n──────────────────────\n"
    body = "\n".join(stats)
    full_response = f"{header}{body}"
    
    await status_msg.edit_text(full_response, parse_mode=ParseMode.HTML)
    return f"Portfolio Status: {', '.join([s.split('</b>')[0].replace('• <b>', '') for s in stats[:3]])}..."

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Synthesizes news and returns the executive summary for memory."""
    if not is_authorized(update): return None
    logger.info(f"▶️ User {update.effective_chat.id} triggered /news")
    
    status_msg = await update.message.reply_text("<i>Analyzing global headlines...</i> ⏳", parse_mode=ParseMode.HTML)
    raw_news = []
    queries = ["geopolitics world", "geopolitics Switzerland", "geopolitics France"]
    
    try:
        for q in queries:
            url = f"https://news.google.com/rss/search?q={q}+when:1d&hl=en-US&gl=US&ceid=US:en"
            res = await asyncio.to_thread(requests.get, url, timeout=10)
            soup = BeautifulSoup(res.content, "xml")
            for item in soup.find_all("item", limit=2):
                raw_news.append(item.title.text)
        
        news_context = "\n".join(raw_news)
        prompt = f"""
        [ROLE]
        You are a highly analytical Geopolitical Briefing Officer.

        [CONTEXT]
        Raw headlines (Last 24h):
        {news_context}
        
        [LANGUAGE ANCHORING - CRITICAL]
        You MUST begin your response by explicitly declaring the detected language of the User Request using exactly one of these tags: [LANG: EN] or [LANG: FR].
        If ambiguous, default to French.
        After outputting the tag, write the ENTIRE rest of the response in that chosen language.

        [TASK]
        Synthesize the headlines into a single, natural, and cohesive paragraph connecting the dots between events.

        [STRICT INSTRUCTIONS]
        1. OBJECTIVITY: Neutral, journalistic tone. No personal opinions.
        2. NO HALLUCINATION: If headlines are missing for a region, focus only on the data available.
        3. FORMATTING: Plain text only. No ALL CAPS titles. No Markdown (no asterisks).
        4. EMOJIS: Include exactly 2 relevant emojis at the end.

        [OUTPUT STRUCTURE]
        [LANG: XX]
        [A single paragraph of 4-6 sentences briefing the client.]
        """
        
        summary = await ask_llm(prompt)
        clean_summary = summary.replace("[LANG: FR]", "").replace("[LANG: EN]", "").replace("*", "").strip()
        
        pref = context.user_data.get('lang', 'fr')
        header_text = "Bilan Géopolitique" if pref == 'fr' else "Geopolitical Briefing"
        
        final_text = f"📰 <b>{header_text}</b>\n──────────────────────\n{clean_summary}"
        await status_msg.edit_text(final_text, parse_mode=ParseMode.HTML)
        return clean_summary

    except Exception as e:
        logger.error(f"❌ News Error: {e}")
        await status_msg.edit_text(f"⚠️ News summary failed: {str(e)}")
        return None