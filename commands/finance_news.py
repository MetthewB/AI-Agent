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
    if not is_authorized(update): return
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
    
    header = "📊 <b>Live Market Portfolio</b>\n━━━━━━━━━━━━━━━━━━━\n"
    body = "\n".join(stats)
    await status_msg.edit_text(f"{header}{body}", parse_mode=ParseMode.HTML)

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
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
        You are a highly analytical Geopolitical Briefing Officer. Your task is to provide a high-level executive summary of current events for a VIP client.

        [CONTEXT]
        Raw headlines from international, Swiss, and French sources (Last 24h):
        {news_context}

        [TASK]
        Synthesize the headlines into a single, natural, and cohesive paragraph connecting the dots between events.

        [STRICT INSTRUCTIONS]
        1. OBJECTIVITY: Maintain a neutral, journalistic tone. No personal opinions.
        2. NO HALLUCINATION: If headlines are missing for a region, focus only on the data available.
        3. PLAIN TEXT ONLY: Absolutely NO HTML tags (no <b>, <i>, etc.).
        4. NO MARKDOWN: Strictly avoid all asterisks (*) and hashtags (#). Use ALL CAPS for emphasis if absolutely necessary.
        5. LANGUAGE: Adhere strictly to the language preference requested.
        6. EMOJIS: Include exactly 2 relevant emojis at the end of the text.

        [OUTPUT STRUCTURE]
        A single paragraph of 4-6 sentences. Start directly with the briefing—no introductory pleasantries.
        """
        
        prompt += get_lang_rule(context)
        summary = await ask_llm(prompt)
        safe_summary = html.escape(summary.replace('*', ''))
        await status_msg.edit_text(f"📰 <b>Geopolitical Briefing</b>\n──────────────────────\n{safe_summary}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ News Error: {e}")
        await status_msg.edit_text(f"⚠️ News summary failed: {str(e)}")