import telebot
from telebot import types
import feedparser
import urllib.parse
import re
import os
from flask import Flask, request
import threading

# --- CONFIGURATION ---
# Your Specific Details are added here
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8300070205:AAF3kfF2P_bSMtnJTc8uJC2waq9d2iRm0i0")
HEMANTH_WHATSAPP_NUMBER = "918970913832" 
RSS_URL = "https://www.karnatakacareers.org/feed/"

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
server = Flask(__name__)

# --- JOB LOGIC ---
def get_job_details(filters, age_limit):
    search_query = " ".join(filters)
    safe_query = urllib.parse.quote(search_query)
    final_url = f"{RSS_URL}?s={safe_query}"
    
    # Parse RSS Feed
    feed = feedparser.parse(final_url)
    matches = []
    
    for entry in feed.entries:
        content = (entry.title + " " + entry.description).lower()
        
        # Age Check
        if age_limit and age_limit.isdigit():
            age_match = re.search(r'(\d{2})\s*(?:-|to)\s*(\d{2})', content)
            if age_match:
                min_age, max_age = map(int, age_match.groups())
                if not (min_age <= int(age_limit) <= max_age):
                    continue 

        # Extract Details
        posts_match = re.search(r'(?:total|no\. of)\s*(?:posts|vacancies)\s*[:\-]?\s*(\d+)', content, re.IGNORECASE)
        total_posts = posts_match.group(1) if posts_match else "See Notification"
        
        date_match = re.search(r'last\s*date\s*[:\-]?\s*(\d{2}[-./]\d{2}[-./]\d{4})', content, re.IGNORECASE)
        last_date = date_match.group(1) if date_match else "Check Notification"

        # Generate WhatsApp Direct Link
        msg_text = f"Hi Hemanth Computers, I want to apply for *{entry.title}*. Please help me."
        wa_link = f"https://wa.me/{HEMANTH_WHATSAPP_NUMBER}?text={urllib.parse.quote(msg_text)}"

        matches.append({
            "title": entry.title, 
            "posts": total_posts, 
            "date": last_date, 
            "link": wa_link
        })
        
        if len(matches) >= 5: break
            
    return matches

# --- BOT COMMANDS ---
user_data = {}

@bot.message_handler(commands=['start', 'hi'])
def send_welcome(message):
    user_data[message.chat.id] = {"filters": []}
    
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("SSLC", "PUC", "Diploma", "BE/B.Tech", "Degree", "Any")
    
    bot.send_message(
        message.chat.id, 
        "👋 *Welcome to Hemanth Computers Bot!*\n\nI can help you find government jobs.\nSelect your **Qualification**:", 
        parse_mode="Markdown", 
        reply_markup=markup
    )
    bot.register_next_step_handler(message, ask_district)

def ask_district(message):
    text = message.text
    if text != "Any":
        user_data[message.chat.id]["filters"].append(text)
        
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("Bangalore", "Mysore", "Belagavi", "Tumkur", "All Karnataka", "Skip")
    
    bot.send_message(message.chat.id, "📍 Select your **District**:", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_department)

def ask_department(message):
    text = message.text
    if text not in ["Skip", "All Karnataka"]:
        user_data[message.chat.id]["filters"].append(text)
        
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("Health", "Police", "Railway", "KPSC", "Court", "Skip")
    
    bot.send_message(message.chat.id, "🏢 Which **Department**?", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_age)

def ask_age(message):
    text = message.text
    if text != "Skip":
        user_data[message.chat.id]["filters"].append(text)
        
    markup = types.ReplyKeyboardRemove()
    bot.send_message(message.chat.id, "🎂 Type your **Age** (e.g., 24):", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, show_results)

def show_results(message):
    age = message.text
    if not age.isdigit():
        bot.send_message(message.chat.id, "⚠️ Please enter a valid number.")
        return bot.register_next_step_handler(message, show_results)
    
    bot.send_message(message.chat.id, "🔍 Searching jobs...")
    
    filters = user_data[message.chat.id]["filters"]
    jobs = get_job_details(filters, age)
    
    if not jobs:
        bot.send_message(message.chat.id, "❌ No matching jobs found.\nType /start to retry.")
    else:
        bot.send_message(message.chat.id, "✅ **Here are the matching jobs:**", parse_mode="Markdown")
        
        for job in jobs:
            text = (
                f"🔹 *{job['title']}*\n"
                f"Vacancies: {job['posts']}\n"
                f"Last Date: {job['date']}\n"
                f"Eligible: ✅"
            )
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📩 Apply via Hemanth Computers", url=job['link']))
            
            bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

# --- WEB SERVER (Required for Render) ---
@server.route('/')
def home():
    return "Bot is running!"

def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    t = threading.Thread(target=run_bot)
    t.start()
    # Get PORT from environment or use 5000 default
    port = int(os.environ.get("PORT", 5000))
    server.run(host="0.0.0.0", port=port)