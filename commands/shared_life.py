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
from modules.utils import get_lang_rule, is_authorized 

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
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /grocery")
    item = " ".join(context.args)
    
    if not item:
        text, reply_markup = build_grocery_ui()
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return

    try:
        grocery_collection.insert_one({"item": item})
        text, reply_markup = build_grocery_ui()
        safe_item = html.escape(item)
        await update.message.reply_text(f"✅ Added <b>{safe_item}</b>!\n\n{text}", reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Grocery Add Error: {e}")
        await update.message.reply_text("⚠️ <i>Failed to add the item. The cart is stuck!</i>", parse_mode=ParseMode.HTML)

async def grocery_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Listens for the user tapping the inline buttons."""
    if not is_authorized(update): return
    
    query = update.callback_query
    await query.answer() 
    
    data = query.data
    
    try:
        if data.startswith("g_rm_"):
            item_id = data.replace("g_rm_", "")
            grocery_collection.delete_one({"_id": ObjectId(item_id)})
            
        elif data == "g_empty":
            grocery_collection.delete_many({})
            
        text, reply_markup = build_grocery_ui()
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)  
      
    except Exception as e:
        logger.error(f"❌ Grocery Callback Error: {e}")
        pass

async def grocery_remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    item_to_remove = " ".join(context.args).strip()
    if not item_to_remove: return
    try:
        docs = list(grocery_collection.find())
        current_items = [doc["item"] for doc in docs]
        matches = [i for i in current_items if item_to_remove.lower() in i.lower()]
        best_match = matches[0] if matches else (difflib.get_close_matches(item_to_remove, current_items, n=1, cutoff=0.3) or [None])[0]
        
        if best_match:
            grocery_collection.delete_one({"item": best_match})
            await update.message.reply_text(f"✅ Removed <b>{html.escape(best_match)}</b>!", parse_mode=ParseMode.HTML)
    except Exception: pass

async def grocery_empty_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    grocery_collection.delete_many({})
    await update.message.reply_text("🧹 <b>Grocery list cleared!</b>", parse_mode=ParseMode.HTML)

async def decide_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    logger.info(f"▶️ User {update.effective_chat.id} triggered /decide")
    options_string = " ".join(context.args)
    
    if not options_string:
        await update.message.reply_text("⚠️ <b>Usage:</b> /decide [option 1], [option 2]\n<i>Example: /decide Pizza, Sushi</i>", parse_mode=ParseMode.HTML)
        return
        
    options = [opt.strip() for opt in options_string.split(",")]
    if len(options) < 2:
        await update.message.reply_text("⚠️ <i>I need at least TWO options to make a decision! Separate them with commas.</i>", parse_mode=ParseMode.HTML)
        return
        
    choice = random.choice(options)
    
    status_msg = await update.message.reply_text("⚖️ <i>Weighing the options...</i>", parse_mode=ParseMode.HTML)
    await asyncio.sleep(1)
    await status_msg.edit_text("🎲 <i>Running the algorithms...</i>", parse_mode=ParseMode.HTML)
    await asyncio.sleep(1.2)
    
    safe_choice = html.escape(choice)
    await status_msg.edit_text(f"🎯 <b>Decision Made:</b>\n\nI have spoken. You are going with: <b>{safe_choice}</b>", parse_mode=ParseMode.HTML)

async def recipe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
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
        await update.effective_message.reply_text("⚠️ <b>Usage:</b> /recipe [ingredient 1], [ingredient 2]", parse_mode=ParseMode.HTML)
        return
        
    status_msg = await update.effective_message.reply_text("👨‍🍳 <i>Putting on my chef's hat and reviewing your ingredients...</i>", parse_mode=ParseMode.HTML)
    
    prompt = f"""
    [ROLE]
    You are an inventive Michelin-star chef who specializes in "fridge-clearing" gourmet cooking.

    [CONTEXT]
    Available ingredients: {ingredients}
    
    [TASK]
    Invent a creative, delicious, and easy-to-make dinner recipe using these ingredients.

    [STRICT INSTRUCTIONS]
    1. INGREDIENT STRICTNESS: Prioritize listed ingredients. Assume a basic pantry (oil, salt, pepper, water), but no other major items.
    2. TONE: Encouraging, professional, and slightly romantic.
    3. PLAIN TEXT ONLY: Absolutely NO HTML tags.
    4. NO MARKDOWN: Strictly avoid all Markdown (no asterisks *, no hashtags #). 
    5. FORMATTING: Use ALL CAPS for section titles. Use standard text bullet points (•) for ingredients and numbers (1., 2.) for steps.

    [OUTPUT STRUCTURE]
    [CATCHY RECIPE TITLE IN ALL CAPS]

    🛒 INGREDIENTS:
    • [Item 1]
    • [Item 2]

    👨‍🍳 INSTRUCTIONS:
    1. [Step 1]
    2. [Step 2]
    """
    prompt += get_lang_rule(context)
    recipe_output = await ask_llm(prompt)
    
    keyboard = [[InlineKeyboardButton("🔄 Re-roll", callback_data="reroll_recipe")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await status_msg.edit_text(f"👨‍🍳 RECIPE FOUND:\n\n{recipe_output}", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"❌ Recipe Display Error: {e}")
        await status_msg.edit_text(f"Recipe output:\n\n{recipe_output}", reply_markup=reply_markup)