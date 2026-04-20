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
def build_grocery_ui():
    """Helper function to fetch the DB and build the interactive inline keyboard."""
    try:
        items_cursor = grocery_collection.find()
        docs = list(items_cursor)
        
        if not docs:
            return "🛒 <b>The grocery list is currently empty!</b>", None
            
        text = f"🛒 <b>Shared Shopping List ({len(docs)} items):</b>\n<i>Tap an item to cross it off.</i>"
        
        keyboard = []
        for doc in docs:
            item_name = doc['item']
            item_id = str(doc['_id'])
            safe_item = html.escape(item_name)
            keyboard.append([InlineKeyboardButton(f"{safe_item}", callback_data=f"g_rm_{item_id}")])
            
        keyboard.append([InlineKeyboardButton("🧹 Empty Entire List", callback_data="g_empty")])
        
        return text, InlineKeyboardMarkup(keyboard)
    except Exception as e:
        logger.error(f"❌ Grocery UI Build Error: {e}")
        return "⚠️ <i>Database error.</i>", None

async def grocery_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    logger.info(f"▶️ User {update.effective_chat.id} triggered /grocery")
    item = " ".join(context.args)
    
    if not item:
        text, reply_markup = build_grocery_ui()
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return text

    try:
        grocery_collection.insert_one({"item": item})
        text, reply_markup = build_grocery_ui()
        safe_item = html.escape(item)
        confirmation = f"✅ Added {safe_item} to the grocery list!"
        await update.message.reply_text(f"{confirmation}\n\n{text}", reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return confirmation
    except Exception as e:
        logger.error(f"❌ Grocery Add Error: {e}")
        await update.message.reply_text("⚠️ <i>Failed to add the item. The cart is stuck!</i>", parse_mode=ParseMode.HTML)
        return None

async def grocery_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    
    query = update.callback_query
    await query.answer() 
    
    data = query.data
    memory_msg = ""
    
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
        text, reply_markup = build_grocery_ui()
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)  
      
    except Exception as e:
        logger.error(f"❌ Grocery Callback Error: {e}")

async def grocery_remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    item_to_remove = " ".join(context.args).strip()
    if not item_to_remove: return None
    try:
        docs = list(grocery_collection.find())
        current_items = [doc["item"] for doc in docs]
        matches = [i for i in current_items if item_to_remove.lower() in i.lower()]
        best_match = matches[0] if matches else (difflib.get_close_matches(item_to_remove, current_items, n=1, cutoff=0.3) or [None])[0]
        
        if best_match:
            grocery_collection.delete_one({"item": best_match})
            msg = f"✅ Removed {best_match} from the grocery list."
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            return msg
        else:
            msg = f"🔍 I couldn't find '{item_to_remove}' on the list."
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            return msg
    except Exception: 
        return None

async def grocery_empty_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    grocery_collection.delete_many({})
    msg = "🧹 Grocery list cleared!"
    await update.message.reply_text(f"<b>{msg}</b>", parse_mode=ParseMode.HTML)
    return msg

async def decide_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return None
    
    if update.message.text and update.message.text.startswith("/decide"):
        raw_text = " ".join(context.args)
        options = [opt.strip() for opt in raw_text.split(",") if opt.strip()]
    else:
        options = context.args
    
    if len(options) < 2:
        await update.message.reply_text(
            "🤔 <i>I couldn't quite distinguish the choices. Try something like 'tacos pizza' or 'tacos ou pizza'!</i>", 
            parse_mode=ParseMode.HTML
        )
        return None
    
    status_msg = await update.message.reply_text("⚖️ <i>Weighing the options...</i>", parse_mode=ParseMode.HTML)
    await asyncio.sleep(1)

    choice = random.choice(options)
    safe_choice = html.escape(choice.upper())
    
    lang = context.user_data.get('lang', 'en')
    if lang == 'fr':
        templates = [
            f"🪐 L'univers a tranché : <b>{safe_choice}</b> !",
            f"🎲 Ma pièce numérique est tombée sur : <b>{safe_choice}</b>.",
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
    
    query = update.callback_query
    if query:
        await query.answer()
        logger.info(f"▶️ User {update.effective_chat.id} triggered re-roll for /recipe")
        ingredients = context.user_data.get('last_recipe', '')
    else:
        logger.info(f"▶️ User {update.effective_chat.id} triggered /recipe")
        ingredients = " ".join(context.args)
        context.user_data['last_recipe'] = ingredients
        
    if not ingredients:
        usage_text = "⚠️ <b>Usage:</b> /recipe [ingrédient 1], [ingrédient 2]"
        await update.effective_message.reply_text(usage_text, parse_mode=ParseMode.HTML)
        return None
        
    status_msg = await update.effective_message.reply_text("👨‍🍳 <i>Reviewing your ingredients and dreaming up a dish...</i>", parse_mode=ParseMode.HTML)
    
    prompt = f"""
    [ROLE]
    You are an inventive Michelin-star chef who specializes in "fridge-clearing" gourmet cooking.

    [CONTEXT]
    Available ingredients: {ingredients}
    
    [LANGUAGE ANCHORING - CRITICAL]
    You MUST begin your response by explicitly declaring the detected language of the User Request using exactly one of these tags: [LANG: EN] or [LANG: FR].
    If ambiguous, default to French.
    After outputting the tag, write the ENTIRE rest of the response in that chosen language.

    [TERMINOLOGY & LOCALIZATION]
    If writing in French, use natural, gourmet terminology. You MUST use these specific translations for your labels:
    - "Ingredients" = "Ingrédients"
    - "Instructions" = "Préparation"

    [TASK]
    Invent a creative, delicious, and easy-to-make dinner recipe using these ingredients.

    [STRICT INSTRUCTIONS]
    1. INGREDIENT STRICTNESS: Prioritize listed ingredients. Assume a basic pantry (oil, salt, pepper, water), but no other major items.
    2. FORMATTING: Use normal Sentence Case or Title Case for all headers. Do NOT use all caps (NO MAJUSCULES). Do not use brackets [] in the output.
    3. PLAIN TEXT ONLY: Absolutely NO HTML tags.
    4. NO MARKDOWN: Strictly avoid all Markdown (no asterisks *, no hashtags #). 
    5. EMOJIS: Use exactly 2 or 3 emojis total.

    [OUTPUT STRUCTURE]
    [LANG: XX]
    🍳 [Catchy Recipe Title]
    ──────────────────────
    [Translated 'Ingredients']:
    • [Item 1]
    • [Item 2]

    [Translated 'Instructions']:
    1. [Step 1]
    2. [Step 2]
    """
    
    recipe_output = await ask_llm(prompt)
    clean_recipe = recipe_output.replace("[LANG: FR]", "").replace("[LANG: EN]", "").replace("*", "").strip()
    
    keyboard = [[InlineKeyboardButton("🔄 Re-roll", callback_data="reroll_recipe")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await status_msg.edit_text(clean_recipe, reply_markup=reply_markup)
        return clean_recipe
    except Exception as e:
        logger.error(f"❌ Recipe Display Error: {e}")
        await status_msg.edit_text("⚠️ Erreur d'affichage, voici la recette brute :\n\n" + clean_recipe)
        return clean_recipe