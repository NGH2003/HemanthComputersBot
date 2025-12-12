import os
import asyncio
import urllib.parse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, PollAnswer
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, PollAnswerHandler
from db import add_user, update_user_profile, delete_user_profile, set_reminder, get_user_docs, add_user_doc, update_user_coins, update_quiz_poll_id, supabase, get_whatsapp_number
from ai_engine import transcribe_audio

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = "@HC_Job_Alerts"

DOC_NAME, DOC_DATE = range(2)

# --- 1. START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    coins = add_user(user.id, user.first_name, user.username, "Unknown", 18, "General", "Male")
    res = supabase.table("users").select("*").eq("user_id", user.id).execute()
    u = res.data[0]
    
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
        f"🪙 **HC Coins:** {coins}\n"
        f"👤 **Profile:** {u.get('qualification')}, {u.get('age')} yrs\n"
        "👇 *Select a service below:*"
    )
    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

# --- 2. QUIZ ANSWER HANDLER (EARN COINS) ---
async def receive_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    user_id = answer.user.id
    selected_option = answer.option_ids[0] # The option user clicked
    
    # 1. Find which quiz this is
    res = supabase.table("quizzes").select("*").eq("poll_id", poll_id).execute()
    if not res.data: return
    
    quiz = res.data[0]
    
    # 2. Check if correct
    if selected_option == quiz['correct_id']:
        # Award 5 Coins
        new_bal = update_user_coins(user_id, 5)
        
        # Send Private Message (If user has started bot)
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 **Correct Answer!**\nYou earned **+5 HC Coins**.\n💰 Total Balance: {new_bal} Coins",
                parse_mode='Markdown'
            )
        except:
            # User hasn't started bot, we silently add coins
            pass

# --- 3. DOCS ---
async def my_docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    docs = get_user_docs(user_id)
    if not docs: msg = "📂 **Locker Empty.**"
    else:
        msg = "📂 **Your Documents:**\n\n"
        for d in docs: msg += f"{'✅' if d['status']=='Valid' else '⚠️'} **{d['doc_name']}** (Exp: {d['expiry_date']})\n"
    kb = [[InlineKeyboardButton("➕ Add New Document", callback_data="add_new_doc")]]
    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

async def start_doc_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.message.reply_text("📤 **Send document/image now.**")
    return DOC_NAME

async def receive_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document: f_id = update.message.document.file_id
    elif update.message.photo: f_id = update.message.photo[-1].file_id
    else: await update.message.reply_text("⚠️ Send PDF/Image."); return DOC_NAME
    context.user_data['file_id'] = f_id
    await update.message.reply_text("📝 **Name this doc?**")
    return DOC_DATE

async def receive_doc_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['doc_name'] = update.message.text
    await update.message.reply_text("📅 **Expiry Date?** (YYYY-MM-DD or None)")
    return ConversationHandler.END

async def receive_doc_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dt = update.message.text
    if dt.lower() == 'none': dt = "2099-01-01"
    add_user_doc(update.effective_user.id, context.user_data['doc_name'], dt, context.user_data['file_id'])
    await update.message.reply_text("✅ **Saved!**"); return ConversationHandler.END

# --- 4. VOICE ---
async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎤 **Listening...**")
    f = await context.bot.get_file(update.message.voice.file_id)
    fb = await f.download_as_bytearray()
    txt = transcribe_audio(fb)
    if not txt: await update.message.reply_text("⚠️ Try again."); return
    await update.message.reply_text(f"🗣️ \"{txt}\"\n🔍 Searching...")
    res = supabase.table("jobs").select("*").eq("is_active", True).ilike("title", f"%{txt}%").limit(5).execute().data
    if res:
        for i in res:
            wl = f"https://wa.me/{get_whatsapp_number()}?text=Details%20{i['title']}"
            kb = [[InlineKeyboardButton("✅ Apply", url=wl)]]
            await update.message.reply_text(f"📢 **{i['title']}**\n{i['summary'][:100]}...", reply_markup=InlineKeyboardMarkup(kb))
    else: await update.message.reply_text("❌ No matches.")

# --- 5. LISTINGS ---
async def show_listings(update: Update, category):
    query = update.callback_query
    if category == "ALL_JOBS": items = supabase.table("jobs").select("*").eq("is_active", True).in_("category", ["GOVT_JOB", "PVT_JOB"]).execute().data
    else: items = supabase.table("jobs").select("*").eq("is_active", True).eq("category", category).execute().data
    if not items: await query.message.reply_text("No updates here."); return
    admin_phone = get_whatsapp_number()
    for item in items:
        wa_link = f"https://wa.me/{admin_phone}?text=Apply%20{item['title']}"
        kb = [[InlineKeyboardButton("🤖 Info", callback_data=f"summary_{item['id']}"), InlineKeyboardButton("✅ Contact", url=wa_link)],
              [InlineKeyboardButton("🔔 Remind Me", callback_data=f"remind_{item['id']}_{item.get('last_date', 'None')}")] ]
        await query.message.reply_text(f"📢 *{item['title']}*\n📅 Ends: {item.get('last_date')}", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

# --- 6. BUTTON HANDLER ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "add_new_doc": await start_doc_upload(update, context); return
    if data.startswith("remind_"):
        jid = data.split("_")[1]
        dt = data.split("_")[2]
        if set_reminder(query.from_user.id, jid, dt): await query.answer("✅ Reminder Set!")
        else: await query.answer("⚠️ Error")
    elif data == "start_register": await query.message.reply_text("Type `/register [Age] [Qual] [Caste] [Gender]`")
    elif data.startswith("cat_"): await show_listings(update, data.split("_", 1)[1])
    elif data.startswith("summary_"):
        jid = data.split("_")[1]
        j = supabase.table("jobs").select("*").eq("id", jid).execute().data[0]
        wl = f"https://wa.me/{get_whatsapp_number()}?text=PDF%20{j['title']}"
        kb = [[InlineKeyboardButton("📄 Request PDF", url=wl)]]
        await query.message.reply_text(f"🤖 **{j['title']}**\n\n{j['summary']}\n\n📂 **Docs:** {j.get('documents_req')}", reply_markup=InlineKeyboardMarkup(kb))
    await query.answer()

# --- 7. BACKGROUND TASKS ---
async def broadcast_quizzes(context: ContextTypes.DEFAULT_TYPE):
    quizzes = supabase.table("quizzes").select("*").eq("is_sent", False).execute().data
    for q in quizzes:
        try:
            if "YOUR_CHANNEL" not in CHANNEL_ID: 
                # SEND POLL (Non-anonymous so we can track who answers!)
                msg = await context.bot.send_poll(
                    chat_id=CHANNEL_ID, 
                    question=q['question'], 
                    options=q['options'], 
                    type='quiz', 
                    correct_option_id=q['correct_id'],
                    is_anonymous=False # <--- CRITICAL FOR EARNING COINS
                )
                # Save Poll ID to DB to verify answers later
                update_quiz_poll_id(q['id'], msg.poll.id)
        except Exception as e: print(f"Quiz Error: {e}")

async def run_bot():
    app = Application.builder().token(TOKEN).build()
    
    doc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_doc_upload, pattern="^add_new_doc$")],
        states={DOC_NAME: [MessageHandler(filters.Document.ALL | filters.PHOTO, receive_doc)], DOC_DATE: [MessageHandler(filters.TEXT, receive_doc_name)]},
        fallbacks=[CommandHandler("cancel", start)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mydocs", my_docs))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # NEW: POLL ANSWER HANDLER
    app.add_handler(PollAnswerHandler(receive_poll_answer))
    
    if app.job_queue: app.job_queue.run_repeating(broadcast_quizzes, interval=60, first=10)
    
    await app.initialize(); await app.start(); await app.updater.start_polling()
    while True: await asyncio.sleep(3600)

