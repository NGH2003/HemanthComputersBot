import telebot
from telebot import types
import feedparser
import urllib.parse
import re
import os
import requests
import json
from flask import Flask, request, render_template_string, redirect, url_for, session, flash
import threading
from bs4 import BeautifulSoup
from functools import wraps
import datetime
import time

# --- 1. CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8300070205:AAF3kfF2P_bSMtnJTc8uJC2waq9d2iRm0i0")

# 🔴 PASTE YOUR NEW GROQ API KEY HERE
GROQ_API_KEY = "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" 

HEMANTH_WHATSAPP_NUMBER = "918970913832"
ADMIN_PASSWORD = "hemanth_admin"
SECRET_KEY = "super_secret_key"
BOT_USERNAME = "HC_Job_Bot" # Change this to your actual bot username without @

DEFAULT_FEEDS = ["https://www.karnatakacareers.org/feed/"]

app_data = {
    "rss_feeds": DEFAULT_FEEDS,
    "total_users": set(),
    "requests_count": 0,
    "logs": []
}

# Language Dictionary for Static Text
LANG = {
    "English": {
        "welcome": "👋 *Hi {}!*\nWelcome to *HC Job Details Bot* 🚀\n\nSelect your language / ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ:",
        "select_qual": "👇 *Select your Qualification:*",
        "select_dist": "📍 Select **District**:",
        "select_dept": "🏢 Which **Department**?",
        "ask_age": "🎂 Type **Age** (e.g., 24) or click 'Any Age':",
        "searching": "🔍 Searching for jobs...",
        "no_jobs": "❌ No jobs found matching your criteria.",
        "apply_btn": "📩 Apply Now",
        "check_eli": "✨ Check Eligibility (AI)",
        "share": "🤝 Share Bot",
        "share_msg": "Find latest Govt Jobs in Karnataka using this bot! Click here: https://t.me/{}",
        "ai_loading": "🤖 AI is reading the notification...",
        "ai_error": "⚠️ AI Busy. Check link manually."
    },
    "Kannada": {
        "welcome": "👋 *ನಮಸ್ಕಾರ {}!*\n*HC ಉದ್ಯೋಗ ಮಾಹಿತಿ ಬಾಟ್‌*ಗೆ ಸ್ವಾಗತ 🚀\n\nಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ:",
        "select_qual": "👇 *ನಿಮ್ಮ ವಿದ್ಯಾರ್ಹತೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ:*",
        "select_dist": "📍 **ಜಿಲ್ಲೆಯನ್ನು** ಆಯ್ಕೆಮಾಡಿ:",
        "select_dept": "🏢 ಯಾವ **ಇಲಾಖೆ**?",
        "ask_age": "🎂 ನಿಮ್ಮ **ವಯಸ್ಸನ್ನು** ಬರೆಯಿರಿ (ಉದಾ: 24) ಅಥವಾ 'ಯಾವುದೇ ವಯಸ್ಸು' ಕ್ಲಿಕ್ ಮಾಡಿ:",
        "searching": "🔍 ಉದ್ಯೋಗಗಳನ್ನು ಹುಡುಕಲಾಗುತ್ತಿದೆ...",
        "no_jobs": "❌ ನಿಮ್ಮ ಆಯ್ಕೆಗೆ ತಕ್ಕ ಉದ್ಯೋಗಗಳು ಇಲ್ಲ.",
        "apply_btn": "📩 ಅರ್ಜಿ ಹಾಕಿ",
        "check_eli": "✨ ಅರ್ಹತೆ ಪರಿಶೀಲಿಸಿ (AI)",
        "share": "🤝 ಬಾಟ್ ಶೇರ್ ಮಾಡಿ",
        "share_msg": "ಕರ್ನಾಟಕದ ಸರ್ಕಾರಿ ಉದ್ಯೋಗಗಳ ಮಾಹಿತಿಗಾಗಿ ಈ ಬಾಟ್ ಬಳಸಿ! ಇಲ್ಲಿ ಕ್ಲಿಕ್ ಮಾಡಿ: https://t.me/{}",
        "ai_loading": "🤖 AI ಅಧಿಸೂಚನೆಯನ್ನು ಓದುತ್ತಿದೆ...",
        "ai_error": "⚠️ AI ಬ್ಯುಸಿ ಇದೆ. ಲಿಂಕ್ ಪರಿಶೀಲಿಸಿ."
    }
}

# Initialize Bot
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
server = Flask(__name__)
server.secret_key = SECRET_KEY

# --- 2. LOGGING HELPER ---
def log_msg(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {message}"
    print(entry)
    app_data["logs"].insert(0, entry)
    if len(app_data["logs"]) > 50: app_data["logs"].pop()

# --- 3. GROQ AI FUNCTION (Llama 3) ---

def clean_html(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    return soup.get_text(separator="\n")

def get_personalized_summary(job_text, user_age, user_qual, language="English"):
    """
    Uses Groq (Llama 3) for super fast, free AI summaries with Language Support
    """
    try:
        age_txt = user_age if user_age and user_age.isdigit() else "Not Provided"
        qual_txt = user_qual if user_qual else "Not Provided"
        
        lang_instruction = "Output strictly in KANNADA language." if language == "Kannada" else "Output in English."

        system_prompt = (
            f"You are a helpful Job Eligibility Assistant. {lang_instruction} "
            "Keep answers short, friendly and precise."
        )
        
        user_prompt = (
            f"Check Eligibility:\n"
            f"User: Age {age_txt}, Qual {qual_txt}\n"
            f"Job: {job_text[:2000]}\n\n"
            f"Output Format:\n"
            f"1. Verdict: '✅ Eligible' or '❌ Not Eligible'.\n"
            f"2. Reason: One short sentence explaining why.\n"
            f"3. Key Details: Post Name, Last Date.\n"
            f"4. Pro Tip: One tip to get selected."
        )

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "llama3-8b-8192", 
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.5,
            "max_tokens": 400
        }

        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            result = response.json()
            ai_text = result['choices'][0]['message']['content']
            app_data["requests_count"] += 1
            return ai_text
        else:
            log_msg(f"Groq Error {response.status_code}: {response.text}")
            return "⚠️ AI Service Busy. Check link directly."

    except Exception as e:
        log_msg(f"Connection Error: {e}")
        return "⚠️ AI Service Busy."

def get_job_details(filters, age_limit):
    matches = []
    log_msg(f"Searching feeds for: {filters}")
    
    for feed_url in app_data["rss_feeds"]:
        try:
            # Create a flexible query
            search_terms = [f for f in filters if "Any" not in f and f not in ["Kannada", "English"]]
            
            if search_terms:
                safe_query = urllib.parse.quote(" ".join(search_terms))
                final_url = f"{feed_url}?s={safe_query}"
            else:
                final_url = feed_url 
                
            feed = feedparser.parse(final_url)
            for entry in feed.entries:
                content = (entry.title + " " + entry.description).lower()
                
                # Age Logic
                if age_limit and age_limit.isdigit():
                    age_match = re.search(r'(\d{2})\s*(?:-|to)\s*(\d{2})', content)
                    if age_match:
                        min_age, max_age = map(int, age_match.groups())
                        if not (min_age <= int(age_limit) <= max_age):
                            continue 

                posts_match = re.search(r'(?:total|no\. of)\s*(?:posts|vacancies)\s*[:\-]?\s*(\d+)', content, re.IGNORECASE)
                total_posts = posts_match.group(1) if posts_match else "View"
                
                # Basic Hemanth Application Link
                msg_text = f"Hi Hemanth, I want to apply for *{entry.title}*."
                wa_link = f"https://wa.me/{HEMANTH_WHATSAPP_NUMBER}?text={urllib.parse.quote(msg_text)}"

                matches.append({
                    "title": entry.title,
                    "posts": total_posts,
                    "link": wa_link,
                    "raw_text": clean_html(entry.description),
                    "id": len(matches)
                })
                if len(matches) >= 5: break
        except Exception as e:
            log_msg(f"Feed Error ({feed_url}): {e}")
            continue
    return matches

# --- 4. ADMIN PANEL (Enhanced) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>HC Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background-color: #f4f6f9; }
        .card { box-shadow: 0 4px 6px rgba(0,0,0,0.1); border:none; }
        .stat-card { text-align:center; padding: 20px; }
        .stat-num { font-size: 2.5rem; font-weight:bold; color: #0d6efd; }
    </style>
</head>
<body>
<nav class="navbar navbar-dark bg-primary mb-4">
  <div class="container"><span class="navbar-brand mb-0 h1">🤖 HC Job Bot Admin</span> <a href="/logout" class="text-white">Logout</a></div>
</nav>
<div class="container">
    
    <div class="row mb-4">
        <div class="col-md-4"><div class="card stat-card"><div class="stat-num">{{ users_count }}</div><div class="text-muted">Total Users</div></div></div>
        <div class="col-md-4"><div class="card stat-card"><div class="stat-num">{{ request_count }}</div><div class="text-muted">AI Queries</div></div></div>
        <div class="col-md-4"><div class="card stat-card"><div class="stat-num">{{ feed_count }}</div><div class="text-muted">Active Feeds</div></div></div>
    </div>

    <div class="card mb-4 border-warning">
        <div class="card-header bg-warning text-dark">📢 <b>Broadcast Message</b> (Send to All Users)</div>
        <div class="card-body">
            <form action="/broadcast" method="post">
                <textarea name="message" class="form-control mb-2" rows="3" placeholder="Type message here... (e.g., 'New KPSC Notification Released! Visit Centre.')" required></textarea>
                <button type="submit" class="btn btn-dark">🚀 Send Broadcast</button>
            </form>
            {% if msg %}
            <div class="alert alert-info mt-2">{{ msg }}</div>
            {% endif %}
        </div>
    </div>

    <div class="row">
        <div class="col-md-6">
            <div class="card mb-3">
                <div class="card-header">Manage RSS Feeds</div>
                <div class="card-body">
                    <ul class="list-group mb-3">
                        {% for feed in feeds %}
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            <small>{{ feed }}</small> 
                            <a href="/delete_feed?url={{ feed }}" class="btn btn-sm btn-danger">X</a>
                        </li>
                        {% endfor %}
                    </ul>
                    <form action="/add_feed" method="post" class="d-flex">
                        <input type="text" name="url" class="form-control me-2" placeholder="https://..." required>
                        <button type="submit" class="btn btn-success">Add</button>
                    </form>
                </div>
            </div>
        </div>

        <div class="col-md-6">
            <div class="card">
                <div class="card-header">System Logs</div>
                <div class="card-body bg-dark text-white" style="height:300px; overflow-y:scroll; font-family:monospace; font-size:12px;">
                    {% for log in logs %}<div>{{ log }}</div>{% endfor %}
                </div>
            </div>
        </div>
    </div>
</div>
</body></html>
"""

LOGIN_HTML = """
<div style="height:100vh; display:flex; justify-content:center; align-items:center; background:#eee;">
    <form method="post" style="padding:40px; background:white; border-radius:10px; box-shadow:0 0 10px rgba(0,0,0,0.1);">
        <h3 style="margin-bottom:20px; text-align:center;">HC Admin</h3>
        <input type="password" name="password" placeholder="Enter Password" style="width:100%; padding:10px; margin-bottom:10px;">
        <button style="width:100%; padding:10px; background:#0d6efd; color:white; border:none; cursor:pointer;">Login</button>
    </form>
</div>
"""

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'): return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

@server.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['password'] == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect('/admin')
    return render_template_string(LOGIN_HTML)

@server.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@server.route('/admin')
@login_required
def admin_panel():
    msg = request.args.get('msg', '')
    return render_template_string(HTML_TEMPLATE, users_count=len(app_data["total_users"]), request_count=app_data["requests_count"], feed_count=len(app_data["rss_feeds"]), feeds=app_data["rss_feeds"], logs=app_data["logs"], msg=msg)

@server.route('/broadcast', methods=['POST'])
@login_required
def broadcast():
    message = request.form.get('message')
    if not message: return redirect('/admin')
    
    count = 0
    # Copy set to list to avoid runtime errors if set changes
    for user_id in list(app_data["total_users"]):
        try:
            bot.send_message(user_id, f"📢 *ANNOUNCEMENT:*\n\n{message}", parse_mode="Markdown")
            count += 1
        except Exception as e:
            log_msg(f"Failed to send to {user_id}: {e}")
            # Optional: remove user if bot was blocked
            # app_data["total_users"].discard(user_id)
            
    log_msg(f"Broadcast sent to {count} users.")
    return redirect(url_for('admin_panel', msg=f"Sent to {count} users!"))

@server.route('/add_feed', methods=['POST'])
@login_required
def add_feed():
    url = request.form.get('url')
    if url: app_data["rss_feeds"].append(url)
    return redirect('/admin')

@server.route('/delete_feed')
@login_required
def delete_feed():
    url = request.args.get('url')
    if url in app_data["rss_feeds"]: app_data["rss_feeds"].remove(url)
    return redirect('/admin')

@server.route('/')
def home(): return redirect('/login')

# --- 5. TELEGRAM LOGIC ---
user_sessions = {}

def get_text(user_id, key):
    lang = user_sessions.get(user_id, {}).get("language", "English")
    return LANG.get(lang, LANG["English"])[key]

@bot.message_handler(commands=['start', 'hi'])
def send_welcome(message):
    app_data["total_users"].add(message.chat.id)
    user_sessions[message.chat.id] = {"filters": [], "language": "English"}
    
    user_name = message.from_user.first_name
    
    # 1. Ask Language First
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True, resize_keyboard=True)
    markup.add("🇬🇧 English", "🇮🇳 Kannada")
    
    # Send a generic welcome first
    bot.send_message(message.chat.id, f"👋 *Hi {user_name}!*\n\nSelect Language / ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ:", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, set_language)

def set_language(message):
    lang_map = {"🇬🇧 English": "English", "🇮🇳 Kannada": "Kannada"}
    selected = lang_map.get(message.text, "English")
    
    user_sessions[message.chat.id]["language"] = selected
    
    # 2. Ask Qualification
    txt = get_text(message.chat.id, "select_qual")
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True, resize_keyboard=True)
    markup.add("SSLC", "PUC", "Diploma", "BE/B.Tech", "Degree", "Any")
    
    bot.send_message(message.chat.id, txt, parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_district)

def ask_district(message):
    if message.text not in ["Any"]: user_sessions[message.chat.id]["filters"].append(message.text)
    
    txt = get_text(message.chat.id, "select_dist")
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True, resize_keyboard=True)
    markup.add("Bangalore", "Mysore", "Belagavi", "Tumkur", "Any")
    
    bot.send_message(message.chat.id, txt, parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_department)

def ask_department(message):
    if message.text not in ["Any"]: user_sessions[message.chat.id]["filters"].append(message.text)
    
    txt = get_text(message.chat.id, "select_dept")
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True, resize_keyboard=True)
    markup.add("Health", "Police", "Railway", "KPSC", "Court", "Any")
    
    bot.send_message(message.chat.id, txt, parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_age)

def ask_age(message):
    if message.text not in ["Any"]: user_sessions[message.chat.id]["filters"].append(message.text)
    
    txt = get_text(message.chat.id, "ask_age")
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True, resize_keyboard=True)
    markup.add("Any Age")
    
    bot.send_message(message.chat.id, txt, parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, show_results)

def show_results(message):
    user_id = message.chat.id
    text = message.text
    age_check = text if text.isdigit() else None
    
    user_sessions[user_id]["age"] = age_check if age_check else "Any"
    
    # Determine Qualification from filters
    qual = "Any"
    for f in user_sessions[user_id]["filters"]:
        if f in ["SSLC", "PUC", "Diploma", "BE/B.Tech", "Degree"]: qual = f
    user_sessions[user_id]["qual"] = qual
    
    bot.send_message(user_id, get_text(user_id, "searching"))
    
    jobs = get_job_details(user_sessions[user_id]["filters"], age_check)
    user_sessions[user_id]["job_cache"] = jobs
    
    if not jobs:
        bot.send_message(user_id, get_text(user_id, "no_jobs"))
        # Add a restart button
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("/start")
        bot.send_message(user_id, "Try again?", reply_markup=markup)
    else:
        for i, job in enumerate(jobs):
            markup = types.InlineKeyboardMarkup()
            markup.row(
                types.InlineKeyboardButton(get_text(user_id, "apply_btn"), url=job['link']),
                types.InlineKeyboardButton(get_text(user_id, "check_eli"), callback_data=f"ai_{i}")
            )
            bot.send_message(user_id, f"🔹 *{job['title']}*\nVacancies: {job['posts']}", parse_mode="Markdown", reply_markup=markup)
        
        # Add Share Button at the end
        share_markup = types.InlineKeyboardMarkup()
        share_url = f"https://t.me/share/url?url={urllib.parse.quote('https://t.me/' + BOT_USERNAME)}"
        share_markup.add(types.InlineKeyboardButton(get_text(user_id, "share"), url=share_url))
        bot.send_message(user_id, "-------", reply_markup=share_markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ai_'))
def handle_ai(call):
    user_id = call.message.chat.id
    idx = int(call.data.split("_")[1])
    try:
        job = user_sessions[user_id]["job_cache"][idx]
        u_age = user_sessions[user_id].get("age", "Not Provided")
        u_qual = user_sessions[user_id].get("qual", "Not Provided")
        u_lang = user_sessions[user_id].get("language", "English")
        
        bot.answer_callback_query(call.id, get_text(user_id, "ai_loading"))
        
        # Pass Language to AI function
        summary = get_personalized_summary(job["raw_text"], u_age, u_qual, u_lang)
        
        bot.send_message(user_id, f"🤖 *AI Analysis:*\n{summary}", parse_mode="Markdown")
    except Exception as e:
        log_msg(f"Callback Error: {e}")
        bot.answer_callback_query(call.id, get_text(user_id, "ai_error"))

if __name__ == "__main__":
    t = threading.Thread(target=bot.infinity_polling)
    t.start()
    server.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
    
