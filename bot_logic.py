import os
import asyncio
import urllib.parse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from db import add_user, supabase, get_whatsapp_number

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = "@YOUR_CHANNEL_USERNAME_HERE" # <--- ADD YOUR CHANNEL ID (e.g. @HC_Jobs)

# --- 1. START MENU & REGISTRATION ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    res = supabase.table("users").select("*").eq("user_id", user.id).execute()
    
    wa_num = get_whatsapp_number()
    tg_user = os.environ.get("ADMIN_TELEGRAM_USERNAME", "HemanthComputers")

    if res.data:
        u = res.data[0]
        msg = f"👋 Namaskara **{u.get('first_name')}**!\n(Profile: {u.get('qualification')})\n\nSelect a category:"
        keyboard = [
            [InlineKeyboardButton("💼 Govt Jobs", callback_data="cat_GOVT_JOB"), 
             InlineKeyboardButton("🏢 Pvt Jobs", callback_data="cat_PVT_JOB")],
            
            [InlineKeyboardButton("📝 Exams", callback_data="cat_EXAM"),
             InlineKeyboardButton("🎓 Scholarships", callback_data="cat_SCHOLARSHIP")],
            
            [InlineKeyboardButton("📂 Application Status", callback_data="check_status")],

            # CONTACT BUTTONS
            [InlineKeyboardButton("🟢 WhatsApp HC", url=f"https://wa.me/{wa_num}"),
             InlineKeyboardButton("🔵 Telegram HC", url=f"https://t.me/{tg_user}")]
        ]
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("Welcome to **HC Bot**!\nPlease Register:\n`/register [Age] [Qual] [Caste] [Gender]`\nEx: `/register 22 Degree 2A Male`", parse_mode='Markdown')

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        # Saves args like: 22, Degree, 2A, Male
        add_user(update.effective_user.id, update.effective_user.first_name, update.effective_user.username, 
                 " ".join(args[1:-2]), int(args[0]), args[-2], args[-1])
        await update.message.reply_text("✅ **Profile Saved!**\nType `/start` to browse.")
    except: await update.message.reply_text("⚠️ Error! Use format: `/register 22 Degree 2A Male`")

# --- 2. LISTINGS & GATEKEEPER LOGIC ---
async def show_listings(update: Update, category):
    query = update.callback_query
    items = supabase.table("jobs").select("*").eq("is_active", True).eq("category", category).execute().data
    
    if not items:
        await query.message.reply_text(f"No active {category}s found.")
        return

    admin_phone = get_whatsapp_number()
    # Inject user profile into WhatsApp message
    user_res = supabase.table("users").select("qualification, age").eq("user_id", query.from_user.id).execute()
    u_details = f"({user_res.data[0]['qualification']}), ({user_res.data[0]['age']})" if user_res.data else "(Unknown)"

    for item in items:
        # Pre-filled WhatsApp Message
        text_msg = f"👋 Hello HC, I want to apply for *{item['title']}*.\nProfile: {u_details}"
        wa_link = f"https://wa.me/{admin_phone}?text={urllib.parse.quote(text_msg)}"

        caption = (
            f"📢 *{item['title']}*\n"
            f"📅 Ends: {item.get('last_date', 'N/A')}\n"
            f"ℹ️ _Contact HC for Link & PDF_" # <--- HIDDEN URL
        )
        keyboard = [[InlineKeyboardButton("🤖 AI Summary", callback_data=f"summary_{item['id']}"),
                     InlineKeyboardButton("✅ Apply (WhatsApp)", url=wa_link)]]
        
        await query.message.reply_text(caption, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("cat_"): await show_listings(update, data.split("_", 1)[1])
    
    elif data == "check_status": 
        # Feature 4: Check Status
        apps = supabase.table("user_applications").select("*").eq("user_id", query.from_user.id).execute().data
        msg = "📂 **Your Applications:**\n\n" + ("\n".join([f"📝 {a['job_title']}: {a['status']}" for a in apps]) if apps else "No active applications.")
        await query.message.reply_text(msg, parse_mode='Markdown')

    elif data.startswith("summary_"):
        job = supabase.table("jobs").select("*").eq("id", data.split("_")[1]).execute().data[0]
        
        # PDF Request Link
        pdf_msg = f"Hello HC, send PDF for *{job['title']}*."
        pdf_wa = f"https://wa.me/{get_whatsapp_number()}?text={urllib.parse.quote(pdf_msg)}"
        
        summary = (
            f"🤖 **AI Summary: {job['title']}**\n\n{job['summary']}\n\n"
            f"📂 **Required Docs:**\n_{job.get('documents_req', 'Ask Admin')}_\n\n"
            f"🔒 *Official Link hidden. Visit Shop to Apply.*"
        )
        keyboard = [[InlineKeyboardButton("📄 Request PDF", url=pdf_wa)]]
        await query.message.reply_text(summary, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    
    await query.answer()

# --- 3. BACKGROUND TASKS (QUIZ) ---
async def broadcast_quizzes(context: ContextTypes.DEFAULT_TYPE):
    """Checks DB for unsent quizzes and blasts them to channel"""
    quizzes = supabase.table("quizzes").select("*").eq("is_sent", False).execute().data
    for q in quizzes:
        try:
            if CHANNEL_ID != "@YOUR_CHANNEL_USERNAME_HERE": # Only send if configured
                await context.bot.send_poll(chat_id=CHANNEL_ID, question=q['question'], options=q['options'], 
                                            type='quiz', correct_option_id=q['correct_id'])
                supabase.table("quizzes").update({"is_sent": True}).eq("id", q['id']).execute()
        except Exception as e: print(f"Quiz Error: {e}")

async def run_bot():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Run Quiz Loop every 60 seconds
    app.job_queue.run_repeating(broadcast_quizzes, interval=60, first=10)
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    while True: await asyncio.sleep(3600)
