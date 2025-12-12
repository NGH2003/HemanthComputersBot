import os
import asyncio
import urllib.parse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from db import add_user, update_user_profile, delete_user_profile, set_reminder, get_user_docs, supabase, get_whatsapp_number
from ai_engine import transcribe_audio

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = "@HC_Job_Alerts" 

# --- 1. START (With Coins) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Check DB & Award Coins
    # We pass dummy values if user exists, just to trigger the login check
    coins = add_user(user.id, user.first_name, user.username, "Unknown", 18, "General", "Male")
    
    res = supabase.table("users").select("*").eq("user_id", user.id).execute()
    u = res.data[0]

    # Fetch Menu
    menu_data = supabase.table("bot_menus").select("*").eq("is_active", True).order("row_order").execute().data
    keyboard = []
    rows = {} 
    for btn in menu_data:
        r = btn['row_order']
        if r not in rows: rows[r] = []
        if btn['action_type'] == 'url': rows[r].append(InlineKeyboardButton(btn['label'], url=btn['action_data']))
        else: rows[r].append(InlineKeyboardButton(btn['label'], callback_data=btn['action_data']))
    for r in sorted(rows.keys()): keyboard.append(rows[r])

    msg = (
        f"👋 **Namaskara {u.get('first_name')}!**\n"
        f"🪙 **HC Coins:** {coins} (Earn rewards!)\n\n"
        f"👤 **Profile:** {u.get('qualification')}, {u.get('age')} yrs\n"
        "👇 *Select a service below:*"
    )
    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

# --- 2. VOICE SEARCH ---
async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles Voice Notes"""
    await update.message.reply_text("🎤 **Listening...** (Processing your voice search)")
    
    # 1. Download Audio
    file = await context.bot.get_file(update.message.voice.file_id)
    file_bytes = await file.download_as_bytearray()
    
    # 2. Transcribe
    text = transcribe_audio(file_bytes)
    if not text:
        await update.message.reply_text("⚠️ Couldn't understand. Please try again.")
        return
        
    await update.message.reply_text(f"🗣️ **You said:** \"{text}\"\n🔍 Searching jobs...")
    
    # 3. Search DB
    results = supabase.table("jobs").select("*").eq("is_active", True).ilike("title", f"%{text}%").limit(5).execute().data
    if results:
        for item in results:
            admin_phone = get_whatsapp_number()
            wa_link = f"https://wa.me/{admin_phone}?text=Details%20for%20{item['title']}"
            kb = [[InlineKeyboardButton("✅ Apply", url=wa_link)]]
            await update.message.reply_text(f"📢 **{item['title']}**\n{item['summary'][:100]}...", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text("❌ No matching jobs found.")

# --- 3. DOC LOCKER COMMAND ---
async def my_docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    docs = get_user_docs(user_id)
    
    if not docs:
        msg = "📂 **Document Locker is Empty.**\nVisit HC Shop to digitize your docs and get expiry alerts!"
    else:
        msg = "📂 **Your Documents:**\n\n"
        for d in docs:
            status = "✅" if d['status'] == 'Valid' else "⚠️"
            msg += f"{status} **{d['doc_name']}** (Exp: {d['expiry_date']})\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

# --- 4. LISTINGS (With Reminder Button) ---
async def show_listings(update: Update, category):
    query = update.callback_query
    if category == "ALL_JOBS": items = supabase.table("jobs").select("*").eq("is_active", True).in_("category", ["GOVT_JOB", "PVT_JOB"]).execute().data
    else: items = supabase.table("jobs").select("*").eq("is_active", True).eq("category", category).execute().data
    
    if not items: await query.message.reply_text("No updates here."); return
    
    admin_phone = get_whatsapp_number()
    for item in items:
        wa_link = f"https://wa.me/{admin_phone}?text=Apply%20{item['title']}"
        
        # REMINDER BUTTON logic
        kb = [
            [InlineKeyboardButton("🤖 Info", callback_data=f"summary_{item['id']}"), InlineKeyboardButton("✅ Contact", url=wa_link)],
            [InlineKeyboardButton("🔔 Remind Me (2 Days Left)", callback_data=f"remind_{item['id']}_{item.get('last_date', 'None')}")]
        ]
        await query.message.reply_text(f"📢 *{item['title']}*\n📅 Ends: {item.get('last_date')}", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

# --- 5. BUTTON HANDLER (Reminders) ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("remind_"):
        parts = data.split("_")
        jid, date_str = parts[1], parts[2]
        if date_str == "None":
            await query.answer("⚠️ No deadline date set for this job.")
            return
            
        if set_reminder(query.from_user.id, jid, date_str):
            await query.answer("✅ Reminder Set! We will alert you 2 days before deadline.")
        else:
            await query.answer("⚠️ Error setting reminder.")
            
    elif data == "start_register": await query.message.reply_text("Type `/register [Age] [Qual] [Caste] [Gender]`") # Simplified
    elif data.startswith("cat_"): await show_listings(update, data.split("_", 1)[1])
    # ... (Keep existing handlers for profile, etc) ...
    
    await query.answer()

# --- 6. BACKGROUND TASKS (Deadline Watchdog) ---
async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Runs daily to send deadline alerts"""
    # In real production, check 'job_reminders' table where reminder_date == TODAY
    # For now, placeholder print
    print("⏰ Checking reminders...")

async def run_bot():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mydocs", my_docs)) # NEW
    app.add_handler(MessageHandler(filters.VOICE, voice_handler)) # NEW VOICE HANDLER
    app.add_handler(CallbackQueryHandler(button_handler))
    
    if app.job_queue:
        # Check reminders every 24 hours (86400s)
        app.job_queue.run_repeating(check_reminders, interval=86400, first=10)
    
    await app.initialize(); await app.start(); await app.updater.start_polling()
    while True: await asyncio.sleep(3600)
