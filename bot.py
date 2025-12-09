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

RSS_FEEDS = [
    "https://www.karnatakacareers.org/feed/",
]

# Initialize AI & Bot
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash') 
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
server = Flask(__name__)
user_data = {}

# --- 2. AI & HELPER FUNCTIONS ---

def clean_html(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    return soup.get_text(separator="\n")

def get_personalized_summary(job_text, user_age, user_qual):
    """
    Asks Gemini to check ELIGIBILITY based on user data 
    and then summarize the job.
    """
    try:
        # Default text if user skipped these inputs
        age_txt = user_age if user_age and user_age.isdigit() else "Not Provided"
        qual_txt = user_qual if user_qual else "Not Provided"

        print(f"🤖 AI Checking: User Age={age_txt}, Qual={qual_txt}")

        prompt = (
            f"Act as a Job Expert. Compare this User Profile with the Job Notification.\n\n"
            f"👤 **User Profile:**\n"
            f"- Age: {age_txt}\n"
            f"- Qualification: {qual_txt}\n\n"
            f"📄 **Job Notification:**\n{job_text[:2500]}\n\n"
            f"**TASK:**\n"
            f"1. **Eligibility Verdict:** Start with '✅ You are Eligible' or '❌ Not Eligible' or '⚠️ May be Eligible'. Explain why in 1 sentence.\n"
            f"2. **Job Summary:** Bullet points for Role, Exact Qualification, Age Limit, Salary (if mentioned), and Last Date.\n"
            f"Keep it friendly and professional."
        )
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"❌ AI ERROR: {e}")
        return f"⚠️ AI Error: {e}"

def get_job_details(filters, age_limit):
    """Searches RSS feeds"""
    matches = []
    
    for feed_url in RSS_FEEDS:
        search_query = " ".join([f for f in filters if "Any" not in f]) # Remove 'Any' for search
        safe_query = urllib.parse.quote(search_query)
        final_url = f"{feed_url}?s={safe_query}"
        
        try:
            feed = feedparser.parse(final_url)
            for entry in feed.entries:
                content = (entry.title + " " + entry.description).lower()
                
                # Regex Age Check (Preliminary)
                if age_limit and age_limit.isdigit():
                    age_match = re.search(r'(\d{2})\s*(?:-|to)\s*(\d{2})', content)
                    if age_match:
                        min_age, max_age = map(int, age_match.groups())
                        if not (min_age <= int(age_limit) <= max_age):
                            continue 

                posts_match = re.search(r'(?:total|no\. of)\s*(?:posts|vacancies)\s*[:\-]?\s*(\d+)', content, re.IGNORECASE)
                total_posts = posts_match.group(1) if posts_match else "See Details"
                
                date_match = re.search(r'last\s*date\s*[:\-]?\s*(\d{2}[-./]\d{2}[-./]\d{4})', content, re.IGNORECASE)
                last_date = date_match.group(1) if date_match else "Check Link"

                raw_clean_text = clean_html(entry.description)
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
        except: continue
    return matches

# --- 3. BOT FLOW ---

@bot.message_handler(commands=['start', 'hi'])
def send_welcome(message):
    user_id = message.chat.id
    # Reset User Data
    user_data[user_id] = {"filters": [], "qual": "Any", "age": "Any"}
    
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("SSLC", "PUC", "Diploma", "BE/B.Tech", "Degree", "Any Qualification")
    
    bot.send_message(user_id, "👋 *Hemanth Computers AI Bot*\n\nSelect Qualification:", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_district)

def ask_district(message):
    user_id = message.chat.id
    text = message.text
    
    # Store Qualification
    user_data[user_id]["qual"] = text
    if text not in ["Any Qualification", "Any"]: 
        user_data[user_id]["filters"].append(text)
        
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("Bangalore", "Mysore", "Belagavi", "Tumkur", "All Karnataka", "Any District")
    bot.send_message(user_id, "📍 Select **District**:", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_department)

def ask_department(message):
    if message.text not in ["Any District", "Skip"]: 
        user_data[message.chat.id]["filters"].append(message.text)
        
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("Health", "Police", "Railway", "KPSC", "Court", "Any Department")
    bot.send_message(message.chat.id, "🏢 Which **Department**?", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_age)

def ask_age(message):
    if message.text not in ["Any Department", "Skip"]: 
        user_data[message.chat.id]["filters"].append(message.text)
        
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("Any Age")
    bot.send_message(message.chat.id, "🎂 Type your **Age** (e.g., 24) or select 'Any Age':", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, show_results)

def show_results(message):
    user_id = message.chat.id
    text = message.text
    
    # Store Age
    if text.isdigit():
        user_data[user_id]["age"] = text
        age_filter = text
    else:
        user_data[user_id]["age"] = "Any" # User selected Any Age
        age_filter = None
    
    bot.send_message(user_id, "🤖 AI is searching internet feeds...")
    
    jobs = get_job_details(user_data[user_id]["filters"], age_filter)
    user_data[user_id]["job_cache"] = jobs
    
    if not jobs:
        bot.send_message(user_id, "❌ No jobs found.")
    else:
        bot.send_message(user_id, "✅ **Matching Jobs:**", parse_mode="Markdown")
        for i, job in enumerate(jobs):
            text = f"🔹 *{job['title']}*\nVacancies: {job['posts']}\nLast Date: {job['date']}"
            markup = types.InlineKeyboardMarkup()
            # Button 1: Apply
            btn_apply = types.InlineKeyboardButton("📩 Apply Now", url=job['link'])
            # Button 2: Personalized AI Check
            btn_ai = types.InlineKeyboardButton("✨ Check My Eligibility", callback_data=f"ai_{i}")
            
            markup.row(btn_apply, btn_ai)
            bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=markup)

# --- 4. NEW PERSONALIZED AI HANDLER ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('ai_'))
def handle_ai_summary(call):
    user_id = call.message.chat.id
    job_index = int(call.data.split("_")[1])
    
    try:
        # Get Job and User Info
        job = user_data[user_id]["job_cache"][job_index]
        u_age = user_data[user_id].get("age", "Not Provided")
        u_qual = user_data[user_id].get("qual", "Not Provided")
        
        bot.answer_callback_query(call.id, "🤖 Analyzing your Profile vs Job...")
        
        # Call Smart AI
        ai_summary = get_personalized_summary(job["raw_text"], u_age, u_qual)
        
        response_text = f"🤖 **AI Analysis for {job['title']}**\n\n{ai_summary}\n\n👇 *Click Apply Now to proceed.*"
        bot.send_message(user_id, response_text, parse_mode="Markdown")
        
    except Exception as e:
        print(f"Error: {e}")
        bot.answer_callback_query(call.id, "Session expired. Please search again.")

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

