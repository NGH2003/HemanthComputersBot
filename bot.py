import telebot
from telebot import types
import feedparser
import urllib.parse
import re
import os
import requests
from flask import Flask
import threading
from bs4 import BeautifulSoup
import google.generativeai as genai

# --- 1. CONFIGURATION ---
# 🔴 PASTE YOUR KEYS HERE
TELEGRAM_BOT_TOKEN = "8300070205:AAF3kfF2P_bSMtnJTc8uJC2waq9d2iRm0i0"
GEMINI_API_KEY = "AIzaSyDA-0mch6ZRr9eARG97bYunAATQQ81gb8k"  
HEMANTH_WHATSAPP_NUMBER = "918970913832"

# 🔴 MULTIPLE RSS FEEDS
RSS_FEEDS = [
    "https://www.karnatakacareers.org/feed/",
    # Add more feeds here if needed
]

# Initialize AI & Bot
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash') 
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
server = Flask(__name__)
user_data = {}

# --- 2. AI & HELPER FUNCTIONS ---

def clean_html(html_text):
    """Removes messy HTML tags to give clean text to AI"""
    soup = BeautifulSoup(html_text, "html.parser")
    return soup.get_text(separator="\n")

def get_ai_summary(job_text):
    """Asks Gemini to summarize the job details"""
    try:
        prompt = (
            "Analyze this job notification and extract the following details strictly:\n"
            "1. Job Role\n2. Age Limit\n3. Qualification\n4. Application Fee\n5. Selection Process\n"
            "6. Last Date\n\n"
            "Keep it short, professional, and use emojis. If info is missing, say 'Not Mentioned'.\n"
            f"Job Text: {job_text[:2000]}" 
        )
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return "⚠️ AI Service Busy. Please check the link directly."

def get_job_details(filters, age_limit):
    """Searches ALL RSS feeds"""
    matches = []
    
    # 1. Loop through all Feeds
    for feed_url in RSS_FEEDS:
        # Create search query
        search_query = " ".join(filters)
        safe_query = urllib.parse.quote(search_query)
        final_url = f"{feed_url}?s={safe_query}"
        
        try:
            feed = feedparser.parse(final_url)
            
            for entry in feed.entries:
                content = (entry.title + " " + entry.description).lower()
                
                # Age Verification
                if age_limit and age_limit.isdigit():
                    age_match = re.search(r'(\d{2})\s*(?:-|to)\s*(\d{2})', content)
                    if age_match:
                        min_age, max_age = map(int, age_match.groups())
                        if not (min_age <= int(age_limit) <= max_age):
                            continue 

                # Basic Regex Extraction
                posts_match = re.search(r'(?:total|no\. of)\s*(?:posts|vacancies)\s*[:\-]?\s*(\d+)', content, re.IGNORECASE)
                total_posts = posts_match.group(1) if posts_match else "See Details"
                
                date_match = re.search(r'last\s*date\s*[:\-]?\s*(\d{2}[-./]\d{2}[-./]\d{4})', content, re.IGNORECASE)
                last_date = date_match.group(1) if date_match else "Check Link"

                # Store raw content for AI later
                raw_clean_text = clean_html(entry.description)

                # WhatsApp Link
                msg_text = f"Hi Hemanth Computers, I want to apply for *{entry.title}*. Please help me."
                wa_link = f"https://wa.me/{HEMANTH_WHATSAPP_NUMBER}?text={urllib.parse.quote(msg_text)}"

                matches.append({
                    "title": entry.title,
                    "posts": total_posts,
                    "date": last_date,
                    "link": wa_link,
                    "raw_text": raw_clean_text, 
                    "id": len(matches) 
                })
                
                if len(matches) >= 5: break
        except:
            continue
            
    return matches

# --- 3. BOT FLOW ---

@bot.message_handler(commands=['start', 'hi'])
def send_welcome(message):
    user_id = message.chat.id
    user_data[user_id] = {"filters": []}
    
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    # Changed 'Any' to 'Any Qualification' for clarity if needed, or keep 'Any'
    markup.add("SSLC", "PUC", "Diploma", "BE/B.Tech", "Degree", "Any Qualification")
    
    bot.send_message(user_id, "👋 *Hemanth Computers AI Bot*\n\nSelect Qualification:", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_district)

def ask_district(message):
    # If they choose "Any Qualification", we don't add a filter
    if message.text not in ["Any Qualification", "Any"]: 
        user_data[message.chat.id]["filters"].append(message.text)
        
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    # 🟢 CHANGED: "Skip" -> "Any District"
    markup.add("Bangalore", "Mysore", "Belagavi", "Tumkur", "All Karnataka", "Any District")
    
    bot.send_message(message.chat.id, "📍 Select **District**:", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_department)

def ask_department(message):
    # 🟢 LOGIC: If "Any District", don't add to filters
    if message.text not in ["Any District", "Skip"]: 
        user_data[message.chat.id]["filters"].append(message.text)
        
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    # 🟢 CHANGED: "Skip" -> "Any Department"
    markup.add("Health", "Police", "Railway", "KPSC", "Court", "Any Department")
    
    bot.send_message(message.chat.id, "🏢 Which **Department**?", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_age)

def ask_age(message):
    # 🟢 LOGIC: If "Any Department", don't add to filters
    if message.text not in ["Any Department", "Skip"]: 
        user_data[message.chat.id]["filters"].append(message.text)
        
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    # 🟢 CHANGED: Added an "Any Age" button so they don't have to type numbers if they don't want to
    markup.add("Any Age")
    
    bot.send_message(message.chat.id, "🎂 Type your **Age** (e.g., 24) or select 'Any Age':", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, show_results)

def show_results(message):
    user_id = message.chat.id
    text = message.text
    
    # Handle Age Logic
    age_to_check = None
    if text.isdigit():
        age_to_check = text
    elif text == "Any Age":
        age_to_check = None # Don't filter by age
    else:
        bot.send_message(user_id, "⚠️ Enter a valid number or click 'Any Age'.")
        return bot.register_next_step_handler(message, show_results)
    
    bot.send_message(user_id, "🤖 AI is searching internet feeds...")
    
    # Pass filters and age to the search function
    jobs = get_job_details(user_data[user_id]["filters"], age_to_check)
    
    user_data[user_id]["job_cache"] = jobs
    
    if not jobs:
        bot.send_message(user_id, "❌ No jobs found with these exact filters.")
    else:
        bot.send_message(user_id, "✅ **Matching Jobs:**", parse_mode="Markdown")
        for i, job in enumerate(jobs):
            text = f"🔹 *{job['title']}*\nVacancies: {job['posts']}\nLast Date: {job['date']}"
            
            markup = types.InlineKeyboardMarkup()
            btn_apply = types.InlineKeyboardButton("📩 Apply Now", url=job['link'])
            btn_ai = types.InlineKeyboardButton("✨ AI Summary", callback_data=f"ai_{i}")
            
            markup.row(btn_apply, btn_ai)
            bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=markup)

# --- 4. AI BUTTON HANDLER ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('ai_'))
def handle_ai_summary(call):
    user_id = call.message.chat.id
    job_index = int(call.data.split("_")[1])
    try:
        job = user_data[user_id]["job_cache"][job_index]
        bot.answer_callback_query(call.id, "🤖 Asking Gemini AI... please wait.")
        ai_summary = get_ai_summary(job["raw_text"])
        response_text = f"🤖 **AI Summary for {job['title']}**\n\n{ai_summary}\n\n👇 *Click Apply Now button above to proceed.*"
        bot.send_message(user_id, response_text, parse_mode="Markdown")
    except Exception as e:
        bot.answer_callback_query(call.id, "Error: Session expired. Search again.")

# --- SERVER ---
@server.route('/')
def home():
    return "Hemanth AI Bot Running"

def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    t = threading.Thread(target=run_bot)
    t.start()
    port = int(os.environ.get("PORT", 5000))
    server.run(host="0.0.0.0", port=port)
