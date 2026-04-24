import html
import random
import difflib
import asyncio
import logging
from bson.objectid import ObjectId
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from modules.ai_core import ask_llm
from modules.config import grocery_collection
from modules.utils import is_authorized 

logger = logging.getLogger(__name__)

# ==========================================
# SHARED LIFE COMMANDS
# ==========================================
def build_grocery_ui(lang: str = 'en'):
    """Helper function to fetch the DB and build the interactive bilingual keyboard."""
    try:
        items_cursor = grocery_collection.find()
        docs = list(items_cursor)
        
        if not docs:
            empty_msg = "🛒 <b>La liste de courses est vide !</b>" if lang == 'fr' else "🛒 <b>The grocery list is currently empty!</b>"
            return empty_msg, None
            
        if lang == 'fr':
            text = f"🛒 <b>Liste de courses partagée ({len(docs)} articles) :</b>\n<i>Appuyez sur un article pour le rayer.</i>"
            empty_btn = "🧹 Vider la liste"
        else:
            text = f"🛒 <b>Shared Shopping List ({len(docs)} items):</b>\n<i>Tap an item to cross it off.</i>"
            empty_btn = "🧹 Empty Entire List"
        
        keyboard = []
        for doc in docs:
            item_name = doc['item']
            item_id = str(doc['_id'])
            keyboard.append([InlineKeyboardButton(f"{item_name}", callback_data=f"g_rm_{item_id}")])
            
        keyboard.append([InlineKeyboardButton(empty_btn, callback_data="g_empty")])
        
        return text, InlineKeyboardMarkup(keyboard)
    except Exception as e:
        logger.error(f"❌ Grocery UI Build Error: {e}")
        err_msg = "⚠️ <i>Erreur de base de données.</i>" if lang == 'fr' else "⚠️ <i>Database error.</i>"
        return err_msg, None


async def grocery_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    logger.info(f"▶️ User {update.effective_chat.id} triggered /grocery")
    
    lang = context.user_data.get('lang', 'fr')
    raw_item_str = " ".join(context.args)
    
    if not raw_item_str:
        text, reply_markup = build_grocery_ui(lang)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return "Displayed the grocery list."

    try:
        cleaned_str = raw_item_str.replace(" et ", ",").replace(" and ", ",")
        items_to_add = [i.strip() for i in cleaned_str.split(",") if i.strip()]
        
        if not items_to_add:
            return None

        grocery_collection.insert_many([{"item": item} for item in items_to_add])
        text, reply_markup = build_grocery_ui(lang)
        
        if len(items_to_add) == 1:
            safe_item = html.escape(items_to_add[0])
            if lang == 'fr':
                confirmation = f"✅ <b>{safe_item}</b> ajouté à la liste !"
            else:
                confirmation = f"✅ Added <b>{safe_item}</b> to the grocery list!"
            mem_return = f"Added {items_to_add[0]} to the grocery list."
        else:
            if lang == 'fr':
                confirmation = f"✅ <b>{len(items_to_add)} articles</b> ajoutés à la liste !"
            else:
                confirmation = f"✅ Added <b>{len(items_to_add)} items</b> to the grocery list!"
            mem_return = f"Added {len(items_to_add)} items to the grocery list: {', '.join(items_to_add)}"
            
        await update.message.reply_text(f"{confirmation}\n\n{text}", reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return mem_return
    
    except Exception as e:
        logger.error(f"❌ Grocery Add Error: {e}")
        err_msg = "⚠️ <i>Échec de l'ajout.</i>" if lang == 'fr' else "⚠️ <i>Failed to add the item.</i>"
        await update.message.reply_text(err_msg, parse_mode=ParseMode.HTML)
        return None


async def grocery_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    
    query = update.callback_query
    await query.answer() 
    
    data = query.data
    memory_msg = ""
    lang = context.user_data.get('lang', 'fr')
    
    try:
        if data.startswith("g_rm_"):
            item_id = data.replace("g_rm_", "")
            item = grocery_collection.find_one({"_id": ObjectId(item_id)})
            if item:
                item_name = item['item']
                grocery_collection.delete_one({"_id": ObjectId(item_id)})
                memory_msg = f"Removed {item_name} from the list via button tap."
            
        elif data == "g_empty":
            grocery_collection.delete_many({})
            memory_msg = "Cleared the entire grocery list via button tap."

        if memory_msg:
            if 'chat_history' not in context.user_data: context.user_data['chat_history'] = []
            context.user_data['chat_history'].append(f"System: {memory_msg}")
            if len(context.user_data['chat_history']) > 6:
                context.user_data['chat_history'] = context.user_data['chat_history'][-6:]
                
        text, reply_markup = build_grocery_ui(lang)
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)  
      
    except Exception as e:
        logger.error(f"❌ Grocery Callback Error: {e}")


async def grocery_remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    
    lang = context.user_data.get('lang', 'fr')
    item_to_remove = " ".join(context.args).strip()
    if not item_to_remove: return None
    
    try:
        docs = list(grocery_collection.find())
        current_items = [doc["item"] for doc in docs]
        matches = [i for i in current_items if item_to_remove.lower() in i.lower()]
        best_match = matches[0] if matches else (difflib.get_close_matches(item_to_remove, current_items, n=1, cutoff=0.3) or [None])[0]
        
        if best_match:
            grocery_collection.delete_one({"item": best_match})
            msg = f"✅ {best_match} retiré de la liste !" if lang == 'fr' else f"✅ Removed {best_match} from the list."
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            return f"Removed {best_match} from the grocery list."
        else:
            msg = f"🔍 Impossible de trouver '{item_to_remove}' sur la liste." if lang == 'fr' else f"🔍 I couldn't find '{item_to_remove}' on the list."
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            return f"Failed to find {item_to_remove} to remove."
    except Exception: 
        return None


async def grocery_empty_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    
    lang = context.user_data.get('lang', 'fr')
    grocery_collection.delete_many({})
    
    msg = "🧹 Liste de courses vidée !" if lang == 'fr' else "🧹 Grocery list cleared!"
    await update.message.reply_text(f"<b>{msg}</b>", parse_mode=ParseMode.HTML)
    return "Emptied the grocery list."


async def decide_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    
    raw_text = update.message.text if update.message and update.message.text else ""
    raw_text_lower = raw_text.lower()
    
    fr_keywords = ["ou", "entre", "décide", "choisis", "lequel", "choisir"]
    en_keywords = ["or", "between", "decide", "choose", "which", "pick"]
    
    if any(word in raw_text_lower.split() for word in fr_keywords):
        lang = 'fr'
        context.user_data['lang'] = 'fr'
    elif any(word in raw_text_lower.split() for word in en_keywords):
        lang = 'en'
        context.user_data['lang'] = 'en'
    else:
        lang = context.user_data.get('lang', 'en')
    
    if raw_text.startswith("/decide"):
        options_text = " ".join(context.args)
        options = [opt.strip() for opt in options_text.split(",") if opt.strip()]
    else:
        options = context.args
    
    if len(options) < 2:
        if lang == 'fr':
            error_msg = "🤔 <i>Je n'ai pas bien compris les choix. Essayez 'tacos pizza' ou 'tacos ou pizza' !</i>"
        else:
            error_msg = "🤔 <i>I couldn't quite distinguish the choices. Try something like 'tacos pizza' or 'tacos or pizza'!</i>"
            
        await update.message.reply_text(error_msg, parse_mode=ParseMode.HTML)
        return None
    
    status_text = "⚖️ <i>Je pèse le pour et le contre...</i>" if lang == 'fr' else "⚖️ <i>Weighing the options...</i>"
    status_msg = await update.message.reply_text(status_text, parse_mode=ParseMode.HTML)
    await asyncio.sleep(1)

    choice = random.choice(options)
    safe_choice = html.escape(choice.upper())
    
    if lang == 'fr':
        templates = [
            f"🪐 L'univers a tranché : <b>{safe_choice}</b> !",
            f"🎲 Ma pièce est tombée sur : <b>{safe_choice}</b>.",
            f"🎯 Choix difficile, mais j'irais avec : <b>{safe_choice}</b>."
        ]
    else:
        templates = [
            f"🪐 The universe has spoken: <b>{safe_choice}</b>!",
            f"🎲 My digital coin landed on: <b>{safe_choice}</b>.",
            f"🎯 Hard choice, but I'd go with <b>{safe_choice}</b>."
        ]
    
    await status_msg.edit_text(random.choice(templates), parse_mode=ParseMode.HTML)
    return choice


async def recipe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    
    # 1. Capture user input and detect language
    user_input = update.message.text if update.message and update.message.text else "Recipe"
    logger.info(f"▶️ User {update.effective_chat.id} triggered /recipe with: {user_input}")
    
    lang = context.user_data.get('lang', 'fr')
    user_input_lower = user_input.lower()
    
    # Fast language sniffing
    if any(w in user_input_lower for w in ["recette", "cuisine", "manger", "boire", "chef"]):
        lang = 'fr'
        context.user_data['lang'] = 'fr'
    elif any(w in user_input_lower for w in ["recipe", "cook", "eat", "drink", "mixologist"]):
        lang = 'en'
        context.user_data['lang'] = 'en'

    query = update.callback_query
    if query:
        await query.answer()
        logger.info(f"▶️ User {update.effective_chat.id} triggered re-roll for /recipe")
        ingredients = context.user_data.get('last_recipe', '')
    else:
        ingredients = " ".join(context.args)
        context.user_data['last_recipe'] = ingredients
        
    if not ingredients:
        usage_text = "⚠️ <b>Usage:</b> /recipe [ingrédient 1], [ingrédient 2]" if lang == 'fr' else "⚠️ <b>Usage:</b> /recipe [ingredient 1], [ingredient 2]"
        await update.effective_message.reply_text(usage_text, parse_mode=ParseMode.HTML)
        return None
        
    status_text = "👨‍🍳 <i>Analyse de vos ingrédients et création d'une recette...</i>" if lang == 'fr' else "👨‍🍳 <i>Reviewing your ingredients and dreaming up a creation...</i>"
    status_msg = await update.effective_message.reply_text(status_text, parse_mode=ParseMode.HTML)
    
    target_lang = "FRENCH" if lang == 'fr' else "ENGLISH"
    
    prompt = f"""
    [ROLE]
    You are an inventive Michelin-star Chef and Master Mixologist who specializes in "fridge-clearing" gourmet creations.

    [CONTEXT]
    User Request: "{user_input}"
    Available ingredients: {ingredients}
    
    [TASK]
    Invent a creative, delicious, and easy-to-make recipe using these ingredients. 
    ADAPTIVE LOGIC: If the ingredients are primarily alcohol, sodas, or juices (like rum and cola), create a Cocktail. Otherwise, create a meal or dessert.

    [STRICT INSTRUCTIONS]
    1. LANGUAGE OVERRIDE: You MUST write the ENTIRE response natively in {target_lang}. Do not drift into English if {target_lang} is FRENCH.
    2. TERMINOLOGY: If in French, use "Ingrédients" and "Préparation" as headers. If in English, use "Ingredients" and "Instructions".
    3. INGREDIENT STRICTNESS: Prioritize listed ingredients. Assume a basic pantry.
    4. CASING: Use normal **Sentence Case** only for the title and steps.
    5. FORMATTING: Plain text ONLY. No Markdown (no asterisks). 
    6. EMOJIS: Use exactly 2 or 3 emojis total.

    [OUTPUT STRUCTURE]
    [Emoji] [Catchy recipe title]
    ─────────────────
    Ingredients:
    • [Item 1]
    
    Instructions:
    1. [Step 1]
    """
    
    recipe_output = await ask_llm(prompt)
    clean_recipe = recipe_output.replace("*", "").strip()
    
    btn_text = "🔄 Nouvelle idée" if lang == 'fr' else "🔄 Re-roll"
    keyboard = [[InlineKeyboardButton(btn_text, callback_data="reroll_recipe")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await status_msg.edit_text(clean_recipe, reply_markup=reply_markup)
        return clean_recipe
    except Exception as e:
        logger.error(f"❌ Recipe Display Error: {e}")
        err_msg = "⚠️ Échec de la génération." if lang == 'fr' else "⚠️ Generation failed."
        await status_msg.edit_text(err_msg)
        return clean_recipe