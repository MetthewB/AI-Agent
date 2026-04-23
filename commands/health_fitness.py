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
    lang = context.user_data.get('lang', 'fr')
    
    if request_details:
        req_lower = request_details.lower()
        if any(w in req_lower for w in ["course", "vélo", "natation", "facile", "fractionné", "muscu", "entraînement"]):
            lang = 'fr'
            context.user_data['lang'] = 'fr'
        elif any(w in req_lower for w in ["run", "bike", "swim", "easy", "intervals", "gym", "workout"]):
            lang = 'en'
            context.user_data['lang'] = 'en'

    if not request_details:
        if lang == 'fr':
            usage = "⚠️ <b>Utilisation :</b> /train [Sport] [Détails]\n<i>Exemple : /train course 5k facile</i>"
        else:
            usage = "⚠️ <b>Usage:</b> /train [Sport] [Specifications]\n<i>Example: /train running easy 5k</i>"
        await update.message.reply_text(usage, parse_mode=ParseMode.HTML)
        return None
        
    status_text = "🏃‍♂️ <i>Synchronisation avec Strava et création de la séance...</i>" if lang == 'fr' else "🏃‍♂️ <i>Syncing with Strava and designing your workout...</i>"
    status_msg = await update.message.reply_text(status_text, parse_mode=ParseMode.HTML)
    
    history_text = await get_recent_strava_activities(limit=5)
    current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")
    
    target_lang = "FRENCH" if lang == 'fr' else "ENGLISH"
    
    prompt = f"""
    [ROLE]
    You are an elite, highly knowledgeable personal trainer and sports scientist.

    [CONTEXT]
    - Today's Date: {current_date}
    - Client Request: "{request_details}"
    - Recent Strava History:
    {history_text}

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
    1. LANGUAGE OVERRIDE: You MUST write the ENTIRE workout plan natively in {target_lang}. Translate the Strava history context into {target_lang} if necessary. Do not drift into English if {target_lang} is FRENCH.
    2. FATIGUE ANALYSIS: If the Strava history shows a heavy session yesterday, suggest a recovery-focused or complementary workout.
    3. FORMATTING: Use Normal Sentence Case or Title Case for headers. Do NOT use all caps (NO MAJUSCULES). 
    4. PLAIN TEXT ONLY: No HTML. No Markdown (no asterisks).
    5. PACE INTELLIGENCE: Prescribe specific target paces (min/km for run, min/100m for swim).
    6. EMOJIS: Use exactly 3 emojis total.

    [OUTPUT STRUCTURE]
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
    clean_workout = workout.replace("*", "").strip()
    try:
        await status_msg.edit_text(clean_workout)
        return clean_workout
    except Exception as e:
        logger.error(f"❌ Train Display Error: {e}")
        error_text = "⚠️ Échec de l'affichage de la séance." if lang == 'fr' else "⚠️ Workout display failed."
        await status_msg.edit_text(error_text)
        return clean_workout


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    logger.info(f"▶️ User {update.effective_chat.id} triggered /stats")
    
    user_request = " ".join(context.args)
    lang = context.user_data.get('lang', 'fr')
    
    if user_request:
        req_lower = user_request.lower()
        if any(w in req_lower for w in ["bilan", "semaine", "résumé", "performance"]):
            lang = 'fr'
            context.user_data['lang'] = 'fr'
        elif any(w in req_lower for w in ["weekly", "summary", "review"]):
            lang = 'en'
            context.user_data['lang'] = 'en'

    status_text = "📊 <i>Accès au coffre-fort Strava...</i>" if lang == 'fr' else "📊 <i>Accessing Strava vault...</i>"
    status_msg = await update.message.reply_text(status_text, parse_mode=ParseMode.HTML)
    
    access_token = await get_strava_access_token()
    if not access_token:
        err_msg = "⚠️ <i>Impossible de se connecter à Strava. Vérifiez vos identifiants API.</i>" if lang == 'fr' else "⚠️ <i>Could not connect to Strava. Check your API credentials.</i>"
        await status_msg.edit_text(err_msg, parse_mode=ParseMode.HTML)
        return None

    seven_days_ago = int(time.time()) - (7 * 24 * 3600)
    url = f"https://www.strava.com/api/v3/athlete/activities?after={seven_days_ago}&per_page=30"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        res = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
        activities = res.json()
        
        if not activities:
            no_act_msg = "📊 Aucune activité enregistrée ces 7 derniers jours. Il est temps de s'y mettre !" if lang == 'fr' else "📊 No activities logged in the last 7 days. Time to get started!"
            await status_msg.edit_text(no_act_msg)
            return no_act_msg
        
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

        target_lang = "FRENCH" if lang == 'fr' else "ENGLISH"
        intent = user_request if user_request else "Standard 7-day performance review"

        prompt = f"""
        [ROLE]
        You are an elite personal trainer and coach. 

        [CONTEXT]
        User Intent: "{intent}"
        Raw Stats (7 Days):
        {raw_stats_summary}

        [TERMINOLOGY & LOCALIZATION]
        If writing in French, use professional sports terminology. Required translations:
        - "7-day Performance Review" = "Bilan Hebdomadaire"
        - "Total Active Time" = "Temps d'activité total"
        - "Breakdown by Sport" = "Répartition par sport"
        - "Run" or "Running" = "Course à pied"
        - "Workout" or "Weight Training" = "Musculation"
        - "Coach's Note" = "Note du coach"

        [TASK]
        Summarize the stats and provide a 2-sentence expert review. 

        [STRICT INSTRUCTIONS]
        1. LANGUAGE OVERRIDE: You MUST write the ENTIRE summary natively in {target_lang}. Translate the Raw Stats (like "Run", "Activities", "Load") into {target_lang}. Do not drift into English if {target_lang} is FRENCH.
        2. RECOVERY ADVICE: If Load > 400, insist on a rest day.
        3. FORMATTING: Use **Sentence Case** or **Title Case** for headers. Do NOT use all caps. 
        4. PLAIN TEXT ONLY: Absolutely NO HTML tags. No Markdown (no asterisks).

        [OUTPUT STRUCTURE]
        📊 [Translated '7-day Performance Review']
        ──────────────────────
        [List the total workouts, time, and load]

        🏅 [Translated 'Breakdown by Sport']
        [List the sports]

        [Translated 'Coach's Note']
        [Your 2-sentence review]
        """
        
        ai_review = await ask_llm(prompt)
        clean_review = ai_review.replace("*", "").strip()
        
        await status_msg.edit_text(clean_review)
        return clean_review
        
    except Exception as e:
        logger.error(f"❌ Stats Logic/Display Error: {e}")
        error_msg = "⚠️ Échec de la génération du résumé des statistiques." if lang == 'fr' else "⚠️ Could not generate stats summary."
        await status_msg.edit_text(error_msg)
        return None