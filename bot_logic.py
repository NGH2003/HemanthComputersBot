import os
import asyncio
import urllib.parse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from db import add_user, supabase, get_whatsapp_number

# Load Token
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = "@HC_Job_Alerts" # <--- Update with your Channel ID

# --- 1. START MENU ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Fetch User from DB
    res = supabase.table("users").select("*").eq("user_id", user.id).execute()
    
    # Fetch Dynamic Menu Buttons
    menu_data = supabase.table("bot_menus").select("*").eq("is_active", True).order("row_order").execute().data
    
    # Build Keyboard
    keyboard = []
    rows = {} 
    for btn in menu_data:
        r = btn['row_order']
        if r not in rows: rows[r] = []
        if btn['action_type'] == 'url':
            rows[r].append(InlineKeyboardButton(btn['label'], url=btn['action_data']))
        else:
            rows[r].append(InlineKeyboardButton(btn['label'], callback_data=btn['action_data']))
    
    for r in sorted(rows.keys()):
        keyboard.append(rows[r])

    if res.data:
        u = res.data[0]
        msg = f"👋 Namaskara **{u.get('first_name')}**!\nWelcome to **HC Citizen Services**.\n(Profile: {u.get('qualification')}, {u.get('age')} yrs)"
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("Welcome!\nPlease Register:\n`/register [Age] [Qual] [Caste] [Gender]`\nEx: `/register 22 Degree 2A Female`", parse_mode='Markdown')

# --- 2. REGISTRATION ---
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) < 4:
             await update.message.reply_text("⚠️ Error! Format: `/register 22 Degree 2A Female`")
             return
        
        # Save to DB
        add_user(update.effective_user.id, update.effective_user.first_name, update.effective_user.username, " ".join(args[1:-2]), int(args[0]), args[-2], args[-1])
        await update.message.reply_text("✅ **Profile Saved!**\nType `/start`.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")

# --- 3. SMART SUGGESTIONS ---
async def suggest_opportunities(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    user_res = supabase.table("users").select("*").eq("user_id", user_id).execute()
    if not user_res.data:
        await query.message.reply_text("⚠️ Please /register first!")
        return
    
    u = user_res.data[0]
    u_age = u['age']; u_qual = u['qualification'].lower(); u_gender = u.get('gender', '').lower(); u_caste = u.get('caste', '').lower()
    
    all_items = supabase.table("jobs").select("*").eq("is_active", True).execute().data
    matched = []
    
    for item in all_items:
        i_qual = item.get('qualification_req', '').lower()
        if not (item.get('min_age',0) <= u_age <= item.get('max_age',100)): continue
        
        if item['category'] == 'SCHEME':
            if "women" in i_qual and "female" not in u_gender: continue
            if ("sc" in i_qual or "st" in i_qual) and ("sc" not in u_caste and "st" not in u_caste): continue
            matched.append(item)
        else:
            if u_qual in i_qual or i_qual in u_qual or "any" in i_qual: matched.append(item)
    
    if not matched:
        await query.message.reply_text(f"🔍 No matches found."); return
    
    admin_phone = get_whatsapp_number()
    await query.message.reply_text(f"🎯 **Found {len(matched)} Matches!**", parse_mode='Markdown')
    
    for item in matched:
        text_msg = f"👋 Hello HC, apply for *{item['title']}* (Matched Profile)."
        wa_link = f"https://wa.me/{admin_phone}?text={urllib.parse.quote(text_msg)}"
        caption = f"✅ *{item['title']}*\n🎓 {item.get('qualification_req')}\n📅 Ends: {item.get('last_date')}"
        keyboard = [[InlineKeyboardButton("🤖 Info", callback_data=f"summary_{item['id']}"), InlineKeyboardButton("✅ Apply", url=wa_link)]]
        await query.message.reply_text(caption, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

# --- 4. LISTINGS ---
async def show_listings(update: Update, category):
    query = update.callback_query
    if category == "RESULT":
        items = supabase.table("jobs").select("*").eq("is_active", True).in_("category", ["RESULT", "KEY_ANSWER"]).execute().data
    else:
        items = supabase.table("jobs").select("*").eq("is_active", True).eq("category", category).execute().data
    
    if not items: await query.message.reply_text("No updates here."); return
    
    admin_phone = get_whatsapp_number()
    for item in items:
        text_msg = f"👋 Hello HC, details for *{item['title']}*?"
        wa_link = f"https://wa.me/{admin_phone}?text={urllib.parse.quote(text_msg)}"
        caption = f"📢 *{item['title']}*\nℹ️ {item.get('summary')[:100]}..."
        keyboard = [[InlineKeyboardButton("🤖 Info", callback_data=f"summary_{item['id']}"), InlineKeyboardButton("✅ Contact", url=wa_link)]]
        await query.message.reply_text(caption, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

# --- 5. BUTTON HANDLER ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data == "suggest_me": await suggest_opportunities(update, context)
    elif data.startswith("cat_"): await show_listings(update, data.split("_", 1)[1])
    elif data == "check_status":
        apps = supabase.table("user_applications").select("*").eq("user_id", query.from_user.id).execute().data
        msg = "📂 **Status:**\n" + ("\n".join([f"{a['job_title']}: {a['status']}" for a in apps]) if apps else "No apps.")
        await query.message.reply_text(msg, parse_mode='Markdown')
    elif data.startswith("summary_"):
        job = supabase.table("jobs").select("*").eq("id", data.split("_")[1]).execute().data[0]
        pdf_msg = f"Hello HC, send PDF for *{job['title']}*."
        pdf_wa = f"https://wa.me/{get_whatsapp_number()}?text={urllib.parse.quote(pdf_msg)}"
        summary = f"🤖 **AI Summary: {job['title']}**\n\n{job['summary']}\n\n📂 **Req:** _{job.get('documents_req', '-')}_\n🔒 *Official Link hidden.*"
        keyboard = [[InlineKeyboardButton("📄 Request Link/PDF", url=pdf_wa)]]
        await query.message.reply_text(summary, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    
    await query.answer()

# --- 6. QUIZ BROADCASTER ---
async def broadcast_quizzes(context: ContextTypes.DEFAULT_TYPE):
    quizzes = supabase.table("quizzes").select("*").eq("is_sent", False).execute().data
    for q in quizzes:
        try:
            # Only broadcast if a real Channel ID is set
            if "YOUR_CHANNEL" not in CHANNEL_ID: 
                await context.bot.send_poll(chat_id=CHANNEL_ID, question=q['question'], options=q['options'], type='quiz', correct_option_id=q['correct_id'])
                supabase.table("quizzes").update({"is_sent": True}).eq("id", q['id']).execute()
        except Exception as e: print(f"Quiz Error: {e}")

# --- 7. MAIN RUNNER (Crucial Function) ---
async def run_bot():
    """Starts the Telegram Bot"""
    print("🤖 Bot Starting...")
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Scheduled Tasks
    if app.job_queue:
        app.job_queue.run_repeating(broadcast_quizzes, interval=60, first=10)
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    # Keep running
    while True:
        await asyncio.sleep(3600)
        
