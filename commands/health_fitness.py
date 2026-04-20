import re
import time
import asyncio
import logging
import datetime
import requests
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from modules.ai_core import ask_llm
from modules.strava_api import get_recent_strava_activities, get_strava_access_token
from modules.utils import is_authorized 

logger = logging.getLogger(__name__)

# ==========================================
# HEALTH & FITNESS COMMANDS
# ==========================================
async def train_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    logger.info(f"▶️ User {update.effective_chat.id} triggered /train")
    
    request_details = " ".join(context.args)
    if not request_details:
        usage = (
            "⚠️ <b>Usage:</b> /train [Sport] [Specifications]\n"
            "<i>Example: /train running easy 5k</i>"
        )
        await update.message.reply_text(usage, parse_mode=ParseMode.HTML)
        return None
        
    status_msg = await update.message.reply_text("🏃‍♂️ <i>Syncing with Strava and designing your workout...</i>", parse_mode=ParseMode.HTML)
    history_text = await get_recent_strava_activities(limit=5)
    current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")
    
    prompt = f"""
    [ROLE]
    You are an elite, highly knowledgeable personal trainer and sports scientist.

    [CONTEXT]
    - Today's Date: {current_date}
    - Client Request: "{request_details}"
    - Recent Strava History:
    {history_text}
    
    [LANGUAGE ANCHORING - CRITICAL]
    You MUST begin your response by explicitly declaring the detected language of the Client Request using exactly one of these tags: [LANG: EN] or [LANG: FR].
    If ambiguous, default to French.
    After outputting the tag, write the ENTIRE rest of the response in that chosen language.

    [TERMINOLOGY & LOCALIZATION]
    If writing in French, use natural, professional sports terminology.
    You MUST use these specific translations for your headers:
    - "Workout Plan" = "Plan d'entraînement"
    - "Recent Training History" = "Historique récent"
    - "Warm-up" = "Échauffement"
    - "Main Set" = "Série principale"
    - "Cool-down" = "Récupération"

    [TASK]
    Design a tailored, one-off workout session based on the goal and current fatigue levels.

    [STRICT INSTRUCTIONS]
    1. FATIGUE ANALYSIS: If the Strava history shows a heavy session yesterday, suggest a recovery-focused or complementary workout.
    2. FORMATTING: Use Normal Sentence Case or Title Case for headers. Do NOT use all caps (NO MAJUSCULES). 
    3. PLAIN TEXT ONLY: No HTML. No Markdown (no asterisks).
    4. PACE INTELLIGENCE: Prescribe specific target paces (min/km for run, min/100m for swim).
    5. EMOJIS: Use exactly 3 emojis total.

    [OUTPUT STRUCTURE]
    [LANG: XX]
    🏃‍♂️ [Translated 'Workout Plan']
    ──────────────────────
    📊 [Translated 'Recent Training History']
    • [History Summary]

    🎯 [Catchy Workout Title]

    🔥 [Translated 'Warm-up']
    • [Details]

    ⚡ [Translated 'Main Set']
    • [Details]

    🧘 [Translated 'Cool-down']
    • [Details]
    """

    workout = await ask_llm(prompt)
    clean_workout = workout.replace("[LANG: FR]", "").replace("[LANG: EN]", "").replace("*", "").strip()
    try:
        await status_msg.edit_text(clean_workout)
        return clean_workout
    except Exception as e:
        logger.error(f"❌ Train Display Error: {e}")
        await status_msg.edit_text(f"⚠️ Workout generated, but display failed. Check logs.")
        return clean_workout

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    logger.info(f"▶️ User {update.effective_chat.id} triggered /stats")
    
    user_request = " ".join(context.args) or "Weekly performance review"

    status_msg = await update.message.reply_text("📊 <i>Accessing Strava vault...</i>", parse_mode=ParseMode.HTML)
    
    access_token = await get_strava_access_token()
    if not access_token:
        await status_msg.edit_text("⚠️ <i>Could not connect to Strava. Check your API credentials.</i>", parse_mode=ParseMode.HTML)
        return None

    seven_days_ago = int(time.time()) - (7 * 24 * 3600)
    url = f"https://www.strava.com/api/v3/athlete/activities?after={seven_days_ago}&per_page=30"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        res = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
        activities = res.json()
        
        if not activities:
            msg = "📊 No activities logged in the last 7 days. Time to get started!"
            await status_msg.edit_text(msg)
            return msg
        
        try:
            from modules.strava_api import sync_activities_to_db
            await sync_activities_to_db(activities)
        except ImportError:
            pass
            
        total_time, total_load, activity_count = 0, 0, len(activities)
        sport_stats = {}
        
        for act in activities:
            sport = act.get('sport_type', 'Activity')
            dist_km = act.get('distance', 0) / 1000
            time_min = act.get('moving_time', 0) / 60

            act_load = 0
            desc = act.get('description', '') or ''
            load_match = re.search(r'(\d+)\s*charge', desc.lower())
            if load_match: act_load = int(load_match.group(1))

            total_time += time_min
            total_load += act_load
            
            if sport not in sport_stats:
                sport_stats[sport] = {'count': 0, 'distance': 0, 'time': 0, 'load': 0}
            sport_stats[sport]['count'] += 1
            sport_stats[sport]['distance'] += dist_km
            sport_stats[sport]['time'] += time_min
            sport_stats[sport]['load'] += act_load

        hrs, mins = int(total_time // 60), int(total_time % 60)
        raw_stats_summary = f"Activities: {activity_count} | Time: {hrs}h {mins}m | Load: {total_load}\n"
        for sport, data in sport_stats.items():
            raw_stats_summary += f"- {sport}: {data['count']} sessions, {data['distance']:.1f}km\n"

        prompt = f"""
        [ROLE]
        You are an elite personal trainer and coach. 

        [CONTEXT]
        User Request: "{user_request}"
        Raw Stats (7 Days):
        {raw_stats_summary}
        
        [LANGUAGE ANCHORING - CRITICAL]
        You MUST begin your response by explicitly declaring the detected language of the User Request using exactly one of these tags: [LANG: EN] or [LANG: FR].
        If ambiguous, default to French.

        [TERMINOLOGY & LOCALIZATION]
        Use professional terminology. Required translations for French:
        - "7-day Performance Review" = "Bilan hebdomadaire"
        - "Total Active Time" = "Temps d'activité total"
        - "Breakdown by Sport" = "Répartition par sport"
        - "Run" or "Running" = "Course à pied"
        - "Workout" or "Weight Training" = "Musculation"
        - "Coach's Note" = "Note du coach"

        [TASK]
        Summarize the stats and provide a 2-sentence expert review. 

        [STRICT INSTRUCTIONS]
        1. RECOVERY ADVICE: If Load > 400, insist on a rest day.
        2. FORMATTING: Use Title Case for headers. No ALL CAPS. 
        3. PLAIN TEXT ONLY: No HTML. No Markdown. 
        4. DIVIDER: Use ────────────────────── after the main title.
        """
        
        ai_review = await ask_llm(prompt)
        clean_review = ai_review.replace("[LANG: FR]", "").replace("[LANG: EN]", "").replace("*", "").strip()
        
        final_display = f"📊 {clean_review}"
        await status_msg.edit_text(final_display)
        return clean_review
        
    except Exception as e:
        logger.error(f"❌ Stats Logic/Display Error: {e}")
        await status_msg.edit_text(f"⚠️ Could not generate stats summary.")
        return None