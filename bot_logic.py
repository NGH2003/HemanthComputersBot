import os
import asyncio
import urllib.parse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from db import add_user, update_user_profile, delete_user_profile, supabase, get_whatsapp_number

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = "@HC_Job_Alerts" 

# --- 1. SMART START COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Check DB
    res = supabase.table("users").select("*").eq("user_id", user.id).execute()
    
    # Fetch Dynamic Menu (Removed Status/Contact from default view logic if needed)
    menu_data = supabase.table("bot_menus").select("*").eq("is_active", True).order("row_order").execute().data
    keyboard = []
    rows = {} 
    for btn in menu_data:
        r = btn['row_order']
        if r not in rows: rows[r] = []
        if btn['action_type'] == 'url':
            rows[r].append(InlineKeyboardButton(btn['label'], url=btn['action_data']))
        else:
            rows[r].append(InlineKeyboardButton(btn['label'], callback_data=btn['action_data']))
    for r in sorted(rows.keys()): keyboard.append(rows[r])

    if res.data:
        # EXISTING USER FLOW
        u = res.data[0]
        msg = (
            f"👋 **Namaskara {u.get('first_name')}!**\n\n"
            f"👤 **Profile:** {u.get('qualification')}, {u.get('age')} yrs\n"
            f"🔍 **Looking for:** Jobs, Schemes, Exams\n\n"
            "👇 *Select a service below:*"
        )
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        # NEW USER FLOW (Updated Text)
        msg = (
            f"👋 **Hey {user.username or user.first_name},**\n"
            "Welcome to HC Citizen Services!\n\n"
            "I can help you find:\n"
            "🏛️ Govt Schemes\n"
            "💼 Govt & Pvt Jobs\n"
            "🎓 Scholarships\n\n"
            "⚠️ **Action Required:** I need to know your details to suggest the right matches."
        )
        # Register Button
        reg_kb = [[InlineKeyboardButton("📝 Create My Profile", callback_data="start_register")]]
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(reg_kb))

# --- 2. REGISTRATION & PROFILE EDIT ---
async def start_register_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered by button"""
    query = update.callback_query
    await query.message.reply_text(
        "📝 **Registration Format:**\n\n"
        "Type your details like this:\n"
        "`/register [Age] [Qualification] [Caste] [Gender]`\n\n"
        "Example:\n`/register 24 Degree 2A Female`",
        parse_mode='Markdown'
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) < 4:
            await update.message.reply_text("⚠️ **Format Error!**\nUse: `/register 24 Degree 2A Female`", parse_mode='Markdown')
            return
        
        # Save
        add_user(update.effective_user.id, update.effective_user.first_name, update.effective_user.username, 
                 " ".join(args[1:-2]), int(args[0]), args[-2], args[-1])
        
        await update.message.reply_text("✅ **Success! Profile Created.**\nTap /start to see your dashboard.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")

async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    res = supabase.table("users").select("*").eq("user_id", user_id).execute()
    
    if res.data:
        u = res.data[0]
        msg = (
            f"👤 **Your Profile**\n\n"
            f"🎓 Qual: **{u.get('qualification')}**\n"
            f"🎂 Age: **{u.get('age')}**\n"
            f"🏷️ Caste: **{u.get('caste')}**\n"
            f"🚻 Gender: **{u.get('gender')}**"
        )
        # Edit Buttons (Added "Edit Full Profile")
        kb = [
            [InlineKeyboardButton("✏️ Edit Age", callback_data="edit_age"),
             InlineKeyboardButton("✏️ Edit Qual", callback_data="edit_qual")],
            [InlineKeyboardButton("🔄 Edit Complete Profile", callback_data="start_register")],
            [InlineKeyboardButton("❌ Delete Profile", callback_data="confirm_delete")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_home")]
        ]
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text("❌ No profile found. Type `/register`.")

async def delete_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to delete profile"""
    user_id = update.effective_user.id
    delete_user_profile(user_id)
    await update.message.reply_text("🗑️ **Profile Deleted.**\nYou can /start again anytime.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows all commands"""
    msg = (
        "🛠️ **HC Bot Commands**\n\n"
        "`/start` - Main Menu\n"
        "`/profile` - View & Edit Profile\n"
        "`/register` - Update Full Profile\n"
        "`/delete_profile` - Delete Account\n"
        "`/set_age [num]` - Quick Age Update\n"
        "`/set_qual [text]` - Quick Qual Update\n"
        "`/help` - Show this list"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def edit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data == "edit_age":
        await query.message.reply_text("🔢 **To change Age:**\nType `/set_age 25`")
    elif data == "edit_qual":
        await query.message.reply_text("🎓 **To change Qualification:**\nType `/set_qual BE`")
    elif data == "confirm_delete":
        user_id = query.from_user.id
        delete_user_profile(user_id)
        await query.message.reply_text("🗑️ **Profile Deleted.**\nType /start to restart.")
    elif data == "back_home":
        await start(update, context)

async def set_field_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text 
    try:
        cmd, val = text.split(" ", 1)
        user_id = update.effective_user.id
        
        if "age" in cmd:
            update_user_profile(user_id, "age", int(val))
            await update.message.reply_text("✅ Age Updated!")
        elif "qual" in cmd:
            update_user_profile(user_id, "qualification", val)
            await update.message.reply_text("✅ Qualification Updated!")
    except:
        await update.message.reply_text("⚠️ Error. Use format: `/set_age 25`")

# --- 3. SUGGESTIONS ---
async def suggest_opportunities(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    user_res = supabase.table("users").select("*").eq("user_id", user_id).execute()
    if not user_res.data: await query.message.reply_text("⚠️ Please /register first!"); return
    
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
    
    if not matched: await query.message.reply_text(f"🔍 No matches found today."); return
    
    admin_phone = get_whatsapp_number()
    await query.message.reply_text(f"🎯 **Found {len(matched)} Matches!**", parse_mode='Markdown')
    for item in matched:
        msg_text = f"Hello HC, apply for {item['title']} (Matched)."
        encoded_msg = urllib.parse.quote(msg_text)
        wa_link = f"https://wa.me/{admin_phone}?text={encoded_msg}"
        caption = f"✅ *{item['title']}*\n🎓 {item.get('qualification_req')}\n📅 Ends: {item.get('last_date')}"
        kb = [[InlineKeyboardButton("🤖 Info", callback_data=f"summary_{item['id']}"), InlineKeyboardButton("✅ Apply", url=wa_link)]]
        await query.message.reply_text(caption, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

# --- 4. LISTINGS ---
async def show_listings(update: Update, category):
    query = update.callback_query
    items = supabase.table("jobs").select("*").eq("is_active", True).eq("category", category).execute().data
    if not items: await query.message.reply_text("No updates here."); return
    
    admin_phone = get_whatsapp_number()
    for item in items:
        msg_text = f"Details for {item['title']}"
        encoded_msg = urllib.parse.quote(msg_text)
        wa_link = f"https://wa.me/{admin_phone}?text={encoded_msg}"
        caption = f"📢 *{item['title']}*\nℹ️ {item.get('summary')[:100]}..."
        kb = [[InlineKeyboardButton("🤖 Info", callback_data=f"summary_{item['id']}"), InlineKeyboardButton("✅ Contact", url=wa_link)]]
        await query.message.reply_text(caption, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data == "start_register": await start_register_flow(update, context)
    elif data == "suggest_me": await suggest_opportunities(update, context)
    elif data.startswith("cat_"): await show_listings(update, data.split("_", 1)[1])
    elif data in ["edit_age", "edit_qual", "back_home", "confirm_delete"]: await edit_handler(update, context)
    elif data.startswith("summary_"):
        job = supabase.table("jobs").select("*").eq("id", data.split("_")[1]).execute().data[0]
        msg_text = f"Hello HC, send PDF for {job['title']}"
        encoded_msg = urllib.parse.quote(msg_text)
        pdf_wa = f"https://wa.me/{get_whatsapp_number()}?text={encoded_msg}"
        summary = f"🤖 **AI Summary: {job['title']}**\n\n{job['summary']}\n\n📂 **Req:** _{job.get('documents_req', '-')}_\n🔒 *Official Link hidden.*"
        kb = [[InlineKeyboardButton("📄 Request Link/PDF", url=pdf_wa)]]
        await query.message.reply_text(summary, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
    await query.answer()

async def broadcast_quizzes(context: ContextTypes.DEFAULT_TYPE):
    # This background task runs every 60s
    quizzes = supabase.table("quizzes").select("*").eq("is_sent", False).execute().data
    for q in quizzes:
        try:
            if "YOUR_CHANNEL" not in CHANNEL_ID: 
                await context.bot.send_poll(chat_id=CHANNEL_ID, question=q['question'], options=q['options'], type='quiz', correct_option_id=q['correct_id'])
                supabase.table("quizzes").update({"is_sent": True}).eq("id", q['id']).execute()
        except Exception as e: 
            print(f"Quiz Error: {e}")

async def run_bot():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("profile", my_profile))
    app.add_handler(CommandHandler("delete_profile", delete_profile_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler(["set_age", "set_qual"], set_field_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    if app.job_queue: app.job_queue.run_repeating(broadcast_quizzes, interval=60, first=10)
    
    await app.initialize(); await app.start(); await app.updater.start_polling()
    while True: await asyncio.sleep(3600)
