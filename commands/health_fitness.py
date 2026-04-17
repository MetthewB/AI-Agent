import re
import html
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
from modules.utils import get_lang_rule, is_authorized 

logger = logging.getLogger(__name__)

# ==========================================
# HEALTH & FITNESS COMMANDS
# ==========================================
async def train_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /train")
    
    request_details = " ".join(context.args)
    if not request_details:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> /train [Sport] [Specifications]\n"
            "<i>Examples:</i>\n"
            "• /train running easy 5k\n"
            "• /train gym push day hypertrophy\n"
            "• /train swimming sprint intervals", 
            parse_mode=ParseMode.HTML
        )
        return
        
    status_msg = await update.message.reply_text("🏃‍♂️ <i>Syncing with Strava and designing your workout...</i>", parse_mode=ParseMode.HTML)
    history_text = await get_recent_strava_activities(limit=5)
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")
    
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

    [TASK]
    Design a tailored, one-off workout session based on the goal and current fatigue levels.

    [STRICT INSTRUCTIONS]
    1. FATIGUE ANALYSIS: Distinguish between sports.
    2. FORMATTING: Use normal Sentence Case or Title Case. Do NOT use all caps (NO MAJUSCULES). Do not use brackets [] in the output.
    3. PACE INTELLIGENCE: 
       - RUNNING: Calculate baseline pace (min/km). Prescribe a target pace in min/km.
       - SWIMMING: Prescribe pace in min/100m.
    4. PLAIN TEXT ONLY: Absolutely NO Markdown (no asterisks *, no hashtags #). 
    5. EMOJIS: Use exactly 3 emojis total, integrated naturally.

    [OUTPUT STRUCTURE]
    [LANG: XX]
    🏃‍♂️ [Translated 'Workout Plan' in Title Case]
    ──────────────────────
    📊 [Translated 'Recent Training History']
    • [DD/MM]: [Sport] - [Distance]km - [Duration] mins (Only show distance if > 0)

    🎯 [Catchy Workout Title]

    🔥 [Translated 'Warm-up']
    • [Drill/distance]

    ⚡ [Translated 'Main Set']
    • [Core workout]

    🧘 [Translated 'Cool-down']
    • [Recovery action]
    """
    
    workout = await ask_llm(prompt)
    clean_workout = workout.replace("[LANG: FR]", "").replace("[LANG: EN]", "").replace("*", "").strip()
    try:
        await status_msg.edit_text(clean_workout)
    except Exception as e:
        logger.error(f"❌ Train Display Error: {e}")
        await status_msg.edit_text(f"⚠️ Erreur: {str(e)}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /stats")
    
    user_request = " ".join(context.args)
    if not user_request and update.message and update.message.text:
        user_request = update.message.text
    if not user_request:
        user_request = "Weekly stats"

    status_msg = await update.message.reply_text("📊 <i>Crunching your weekly numbers...</i>", parse_mode=ParseMode.HTML)
    
    access_token = await get_strava_access_token()
    if not access_token:
        await status_msg.edit_text("⚠️ <i>Could not connect to Strava / Impossible de se connecter à Strava.</i>", parse_mode=ParseMode.HTML)
        return

    seven_days_ago = int(time.time()) - (7 * 24 * 3600)
    url = f"https://www.strava.com/api/v3/athlete/activities?after={seven_days_ago}&per_page=30"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        res = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
        activities = res.json()
        
        if not activities:
            await status_msg.edit_text("📊 <b>Weekly Stats</b>\n\nYou haven't logged any activities in the last 7 days. Time to get moving! / Aucune activité ces 7 derniers jours. Il est temps de bouger ! 🏃‍♂️💨", parse_mode=ParseMode.HTML)
            return
        
        logger.info(f"🚀 Triggering background PostgreSQL sync for {len(activities)} weekly activities...")
        from modules.strava_api import sync_activities_to_db
        await sync_activities_to_db(activities)
            
        total_time = 0
        total_load = 0
        activity_count = len(activities)
        sport_stats = {}
        
        for act in activities:
            sport = act.get('sport_type', 'Activity')
            dist_km = act.get('distance', 0) / 1000
            time_min = act.get('moving_time', 0) / 60
            
            desc = act.get('description', '') or ''
            act_load = 0
            if "charge d'entraînement" in desc:
                match = re.search(r'(\d+)\s*charge', desc)
                if match: act_load = int(match.group(1))

            total_time += time_min
            total_load += act_load
            
            if sport not in sport_stats:
                sport_stats[sport] = {'count': 0, 'distance': 0, 'time': 0, 'load': 0}
                
            sport_stats[sport]['count'] += 1
            sport_stats[sport]['distance'] += dist_km
            sport_stats[sport]['time'] += time_min
            sport_stats[sport]['load'] += act_load

        hrs = int(total_time // 60)
        mins = int(total_time % 60)
        
        stats_lines = [
            f"Total Workouts: {activity_count}",
            f"Total Active Time: {hrs}h {mins}m"
        ]
        if total_load > 0:
            stats_lines.append(f"Total Coros Load: {total_load}")
            
        stats_lines.append("\nBreakdown by Sport:")
        for sport, data in sport_stats.items():
            s_hrs = int(data['time'] // 60)
            s_mins = int(data['time'] % 60)
            time_str = f"{s_hrs}h {s_mins}m" if s_hrs > 0 else f"{s_mins}m"
            
            line = f"- {sport}: {data['count']} session(s) | {time_str}"
            if data['distance'] > 0:
                line += f" | {data['distance']:.1f} km"
            if data['load'] > 0:
                line += f" | Load: {data['load']}"
            stats_lines.append(line)
            
        raw_stats_text = "\n".join(stats_lines)
        
        prompt = f"""
        [ROLE]
        You are an elite personal trainer. 

        [CONTEXT]
        User Request: "{user_request}"
        Raw Client Stats (Last 7 days):
        {raw_stats_text}
        
        [LANGUAGE ANCHORING - CRITICAL]
        You MUST begin your response by explicitly declaring the detected language of the User Request using exactly one of these tags: [LANG: EN] or [LANG: FR].
        If ambiguous, default to French.
        After outputting the tag, write the ENTIRE rest of the response in that chosen language. Translate all headers and sport names accordingly.

        [TASK]
        Format the client's weekly stats into a clean summary and add a short, 2-sentence encouraging review at the end based on their mix of sports.

        [STRICT INSTRUCTIONS]
        1. SMART GYM LOGIC: If they did gym/weight training with 0 Coros Load, DO NOT say they were resting. Acknowledge the strength work!
        2. RECOVERY PROTOCOL: If Total Coros Load > 400, strictly advise them to prioritize recovery.
        3. DATA ACCURACY: Do not alter the numbers from the Raw Client Stats. Just format and translate them.
        4. CASING: Use normal Sentence Case or Title Case for all headers and labels. Do NOT use all caps (NO MAJUSCULES).
        5. PLAIN TEXT ONLY: Absolutely NO HTML tags (no <b>, no <i>).
        6. NO MARKDOWN: Absolutely NO asterisks (*) or hashtags (#). 
        7. EMOJIS: Use emojis tastefully for the headers and the coach's note.

        [OUTPUT STRUCTURE]
        [LANG: XX]
        📊 [Translated '7-day Performance Review']
        ──────────────────────
        [Translated 'Total Workouts']: [Value]
        [Translated 'Total Active Time']: [Value]
        (Include Load if it exists in raw data)

        🏅 [Translated 'Breakdown by Sport']:
        • [Translated Sport]: [Count] session(s) | [Time] | [Distance]

        [Translated "Coach's Note"]:
        [Your 2-sentence review]
        """
        
        ai_review = await ask_llm(prompt)
        clean_review = ai_review.replace("[LANG: FR]", "").replace("[LANG: EN]", "").replace("*", "").strip()
        await status_msg.edit_text(clean_review)
        
    except Exception as e:
        logger.error(f"❌ Stats Command Error: {e}")
        await status_msg.edit_text(f"⚠️ Error fetching stats: {str(e)}")
        
    except Exception as e:
            logger.error(f"❌ Stats Logic/Display Error: {e}")
            await status_msg.edit_text(f"⚠️ Stats summary failed: {str(e)}")