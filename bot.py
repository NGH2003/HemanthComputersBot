import telebot
from telebot import types
import feedparser
import urllib.parse
import re
import os
import requests
import json
from flask import Flask, request, render_template_string, redirect, url_for, session
import threading
from bs4 import BeautifulSoup
from functools import wraps
import datetime
import time

# --- 1. CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8300070205:AAF3kfF2P_bSMtnJTc8uJC2waq9d2iRm0i0")
GROQ_API_KEY = "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" # 🔴 PASTE KEY HERE

HEMANTH_WHATSAPP_NUMBER = "918970913832"
ADMIN_PASSWORD = "hemanth_admin"
SECRET_KEY = "super_secret_key"
BOT_USERNAME = "HC_Job_Bot" 

DEFAULT_FEEDS = ["https://www.karnatakacareers.org/feed/"]

app_data = {
    "rss_feeds": DEFAULT_FEEDS,
    "total_users": set(),
    "requests_count": 0,
    "logs": []
}

# Language Dictionary
LANG = {
    "English": {
        "welcome": "👋 *Hi {}!*\nSelect Language:",
        "searching": "🔍 Searching for jobs...",
        "no_jobs": "❌ No jobs found matching your criteria.",
        "apply_btn": "📩 Apply / WhatsApp",
        "check_eli": "👤 Check My Eligibility",
        "summary_btn": "📝 Full Notification Summary",
        "share": "🤝 Share Bot",
        "ai_loading": "🤖 AI is reading...",
        "ai_error": "⚠️ Server Busy. Try link directly."
    },
    "Kannada": {
        "welcome": "👋 *ನಮಸ್ಕಾರ {}!*\nಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ:",
        "searching": "🔍 ಉದ್ಯೋಗಗಳನ್ನು ಹುಡುಕಲಾಗುತ್ತಿದೆ...",
        "no_jobs": "❌ ಉದ್ಯೋಗಗಳು ಇಲ್ಲ.",
        "apply_btn": "📩 ಅರ್ಜಿ ಹಾಕಿ",
        "check_eli": "👤 ನನ್ನ ಅರ್ಹತೆ ಪರಿಶೀಲಿಸಿ",
        "summary_btn": "📝 ಪೂರ್ಣ ಸಾರಾಂಶ (Summary)",
        "share": "🤝 ಶೇರ್ ಮಾಡಿ",
        "ai_loading": "🤖 AI ಓದುತ್ತಿದೆ...",
        "ai_error": "⚠️ ಸರ್ವರ್ ಬ್ಯುಸಿ ಇದೆ."
    }
}

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
server = Flask(__name__)
server.secret_key = SECRET_KEY

# --- 2. LOGGING & UTILS ---
def log_msg(message):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {message}"
    print(entry)
    app_data["logs"].insert(0, entry)
    if len(app_data["logs"]) > 100: app_data["logs"].pop()

def clean_html(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    return soup.get_text(separator="\n")

def extract_date(text):
    # Regex to find dates like 31-12-2025 or 31/12/2025
    match = re.search(r'(\d{2}[-./]\d{2}[-./]\d{4})', text)
    return match.group(1) if match else "Check Link"

# --- 3. ROBUST AI ENGINE (With Retry Logic) ---
def call_groq_ai(system_prompt, user_prompt):
    """
    Tries to call Groq AI up to 3 times if it fails (Retries)
    """
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "llama3-8b-8192", 
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.5,
        "max_tokens": 500
    }

    # RETRY LOGIC (Fixes 'Service Busy')
    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                app_data["requests_count"] += 1
                return response.json()['choices'][0]['message']['content']
            elif response.status_code == 429: # Rate Limit
                time.sleep(2) # Wait 2 seconds and try again
                continue
            else:
                log_msg(f"Groq Error: {response.status_code}")
                break
        except Exception as e:
            log_msg(f"Connection Error: {e}")
            time.sleep(1)
    
    return None # Failed after 3 tries

def get_ai_response(mode, job_text, user_data):
    """
    mode: 'eligibility' or 'summary'
    """
    language = user_data.get("language", "English")
    lang_instruction = "Output strictly in KANNADA language." if language == "Kannada" else "Output in English."

    if mode == "eligibility":
        age = user_data.get("age", "N/A")
        qual = user_data.get("qual", "N/A")
        system_prompt = f"You are a Job Eligibility Assistant. {lang_instruction} Be short and precise."
        user_prompt = (
            f"User: Age {age}, Qual {qual}\nJob: {job_text[:2000]}\n\n"
            f"1. Verdict (Eligible/Not Eligible)\n2. Reason\n3. Important Dates"
        )
    else: # Summary Mode
        system_prompt = f"You are a News Reporter summarizing job notifications. {lang_instruction} Use Bullet points."
        user_prompt = (
            f"Summarize this job notification:\n{job_text[:2000]}\n\n"
            f"Include:\n- Post Name\n- Total Vacancies\n- Age Limit\n- Qualification\n- Selection Process\n- Fees"
        )

    response = call_groq_ai(system_prompt, user_prompt)
    return response if response else "⚠️ AI Service Busy. Please open the link to read details."

# --- 4. RSS PARSER ---
def get_job_details(filters, age_limit):
    matches = []
    log_msg(f"Searching: {filters}")
    
    for feed_url in app_data["rss_feeds"]:
        try:
            search_terms = [f for f in filters if "Any" not in f and f not in ["Kannada", "English"]]
            final_url = f"{feed_url}?s={urllib.parse.quote(' '.join(search_terms))}" if search_terms else feed_url
            
            feed = feedparser.parse(final_url)
            for entry in feed.entries:
                content = (entry.title + " " + entry.description).lower()
                clean_desc = clean_html(entry.description)
                
                # Filter Logic
                if age_limit and age_limit.isdigit():
                    age_match = re.search(r'(\d{2})\s*(?:-|to)\s*(\d{2})', content)
                    if age_match:
                        min_a, max_a = map(int, age_match.groups())
                        if not (min_a <= int(age_limit) <= max_a): continue 

                # Extract Details
                posts_match = re.search(r'(?:total|no\. of)\s*(?:posts|vacancies)\s*[:\-]?\s*(\d+)', content, re.IGNORECASE)
                total_posts = posts_match.group(1) if posts_match else "View Notification"
                last_date = extract_date(clean_desc)

                wa_msg = f"Hi Hemanth, apply for *{entry.title}*."
                wa_link = f"https://wa.me/{HEMANTH_WHATSAPP_NUMBER}?text={urllib.parse.quote(wa_msg)}"

                matches.append({
                    "title": entry.title,
                    "posts": total_posts,
                    "date": last_date,
                    "link": wa_link,
                    "raw_text": clean_desc,
                    "id": len(matches)
                })
                if len(matches) >= 5: break
        except: continue
    return matches

# --- 5. MODERN ADMIN PANEL ---
HTML_ADMIN = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HC Job Bot | Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #1a1d21; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
        .sidebar { height: 100vh; background: #212529; padding-top: 20px; border-right: 1px solid #343a40; }
        .card { background-color: #2c3035; border: none; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.2); margin-bottom: 20px; }
        .card h5 { color: #adb5bd; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 1px; }
        .stat-num { font-size: 2.5rem; font-weight: 700; color: #0d6efd; }
        .list-group-item { background-color: #2c3035; color: white; border-color: #343a40; }
        .btn-brand { background-color: #0d6efd; color: white; }
        .log-box { font-family: monospace; font-size: 0.8rem; color: #00ff9d; max-height: 400px; overflow-y: auto; background: #000; padding: 15px; border-radius: 8px; }
    </style>
</head>
<body>
<div class="container-fluid">
    <div class="row">
        <div class="col-md-2 sidebar d-none d-md-block">
            <h4 class="text-center text-white mb-4">🚀 HC Admin</h4>
            <div class="d-grid gap-2 px-3">
                <a href="/admin" class="btn btn-brand mb-2">Dashboard</a>
                <a href="/logout" class="btn btn-outline-danger">Logout</a>
            </div>
            <div class="mt-4 px-3 text-muted text-center" style="font-size:12px;">
                Running on V2.0<br>Status: 🟢 Online
            </div>
        </div>

        <div class="col-md-10 p-4">
            
            <div class="row mb-4">
                <div class="col-md-4">
                    <div class="card p-3 text-center">
                        <h5>Total Users</h5>
                        <div class="stat-num">{{ users_count }}</div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card p-3 text-center">
                        <h5>AI Requests</h5>
                        <div class="stat-num text-warning">{{ request_count }}</div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card p-3 text-center">
                        <h5>Active Feeds</h5>
                        <div class="stat-num text-success">{{ feed_count }}</div>
                    </div>
                </div>
            </div>

            <div class="card p-4">
                <h4 class="mb-3 text-white">📢 Broadcast Announcement</h4>
                <form action="/broadcast" method="post">
                    <div class="input-group">
                        <input type="text" name="message" class="form-control bg-dark text-white border-secondary" placeholder="Type message to send to all users..." required>
                        <button type="submit" class="btn btn-warning fw-bold">SEND 🚀</button>
                    </div>
                </form>
                {% if msg %}<div class="alert alert-success mt-2 py-1">{{ msg }}</div>{% endif %}
            </div>

            <div class="row">
                <div class="col-md-6">
                    <div class="card p-3 h-100">
                        <h4 class="text-white mb-3">📡 RSS Feeds</h4>
                        <ul class="list-group mb-3">
                            {% for feed in feeds %}
                            <li class="list-group-item d-flex justify-content-between align-items-center">
                                <div class="text-truncate" style="max-width: 250px;">{{ feed }}</div>
                                <a href="/delete_feed?url={{ feed }}" class="btn btn-sm btn-danger">Remove</a>
                            </li>
                            {% endfor %}
                        </ul>
                        <form action="/add_feed" method="post" class="d-flex">
                            <input type="text" name="url" class="form-control me-2 bg-dark text-white border-secondary" placeholder="https://..." required>
                            <button type="submit" class="btn btn-success">Add</button>
                        </form>
                    </div>
                </div>

                <div class="col-md-6">
                    <div class="card p-3 h-100">
                        <h4 class="text-white mb-3">💻 Live Logs</h4>
                        <div class="log-box">
                            {% for log in logs %}<div>> {{ log }}</div>{% endfor %}
                        </div>
                    </div>
                </div>
            </div>

        </div>
    </div>
</div>
</body>
</html>
"""

# --- FLASK ROUTES ---
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
    return render_template_string("""<body style="background:#1a1d21; display:flex; justify-content:center; align-items:center; height:100vh;"><form method="post" style="padding:40px; background:#2c3035; border-radius:10px;"><h3 style="color:white; text-align:center;">🔐 Admin Login</h3><input type="password" name="password" style="width:100%; padding:10px; margin:15px 0;" placeholder="Password"><button style="width:100%; padding:10px; background:#0d6efd; color:white; border:none; cursor:pointer;">Enter</button></form></body>""")

@server.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@server.route('/admin')
@login_required
def admin_panel():
    msg = request.args.get('msg', '')
    return render_template_string(HTML_ADMIN, users_count=len(app_data["total_users"]), request_count=app_data["requests_count"], feed_count=len(app_data["rss_feeds"]), feeds=app_data["rss_feeds"], logs=app_data["logs"], msg=msg)

@server.route('/broadcast', methods=['POST'])
@login_required
def broadcast():
    msg = request.form.get('message')
    count = 0
    for uid in list(app_data["total_users"]):
        try:
            bot.send_message(uid, f"📢 *ALERT:*\n\n{msg}", parse_mode="Markdown")
            count += 1
        except: pass
    return redirect(url_for('admin_panel', msg=f"Sent to {count} users."))

@server.route('/add_feed', methods=['POST'])
@login_required
def add_feed():
    if url := request.form.get('url'): app_data["rss_feeds"].append(url)
    return redirect('/admin')

@server.route('/delete_feed')
@login_required
def delete_feed():
    if url := request.args.get('url'): 
        if url in app_data["rss_feeds"]: app_data["rss_feeds"].remove(url)
    return redirect('/admin')

@server.route('/')
def home(): return redirect('/login')

# --- 6. TELEGRAM BOT LOGIC ---
user_sessions = {}

def get_txt(uid, key):
    lang = user_sessions.get(uid, {}).get("language", "English")
    return LANG.get(lang, LANG["English"]).get(key, "")

@bot.message_handler(commands=['start', 'hi'])
def start(message):
    app_data["total_users"].add(message.chat.id)
    user_sessions[message.chat.id] = {"filters": [], "language": "English"}
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
    markup.add("🇬🇧 English", "🇮🇳 Kannada")
    bot.send_message(message.chat.id, "👋 *Welcome!*\n\nSelect Language / ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ:", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, set_lang)

def set_lang(msg):
    lang = "Kannada" if "Kannada" in msg.text else "English"
    user_sessions[msg.chat.id]["language"] = lang
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("SSLC", "PUC", "Diploma", "Degree", "Any")
    bot.send_message(msg.chat.id, "🎓 Select Qualification:", reply_markup=markup)
    bot.register_next_step_handler(msg, set_qual)

def set_qual(msg):
    user_sessions[msg.chat.id]["qual"] = msg.text
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("Bangalore", "Mysore", "Any District")
    bot.send_message(msg.chat.id, "📍 Select District:", reply_markup=markup)
    bot.register_next_step_handler(msg, set_dist)

def set_dist(msg):
    user_sessions[msg.chat.id]["filters"].append(msg.text)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Any Age")
    bot.send_message(msg.chat.id, "🎂 Type Age (e.g. 24):", reply_markup=markup)
    bot.register_next_step_handler(msg, show_jobs)

def show_jobs(msg):
    uid = msg.chat.id
    age = msg.text if msg.text.isdigit() else None
    user_sessions[uid]["age"] = age if age else "Any"
    
    bot.send_message(uid, get_txt(uid, "searching"))
    jobs = get_job_details(user_sessions[uid]["filters"], age)
    user_sessions[uid]["job_cache"] = jobs
    
    if not jobs:
        bot.send_message(uid, get_txt(uid, "no_jobs"))
        return

    for i, job in enumerate(jobs):
        # DETAILED MESSAGE FORMAT
        caption = (
            f"🔹 *{job['title']}*\n\n"
            f"📅 *Deadline:* {job['date']}\n"
            f"💼 *Vacancies:* {job['posts']}"
        )
        
        # THREE BUTTONS
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(get_txt(uid, "apply_btn"), url=job['link']))
        markup.add(
            types.InlineKeyboardButton(get_txt(uid, "check_eli"), callback_data=f"eli_{i}"),
            types.InlineKeyboardButton(get_txt(uid, "summary_btn"), callback_data=f"sum_{i}")
        )
        
        bot.send_message(uid, caption, parse_mode="Markdown", reply_markup=markup)
    
    # Share Link
    sh_markup = types.InlineKeyboardMarkup()
    sh_markup.add(types.InlineKeyboardButton(get_txt(uid, "share"), url=f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME}"))
    bot.send_message(uid, "-----------------", reply_markup=sh_markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    uid = call.message.chat.id
    try:
        prefix, idx = call.data.split("_")
        job = user_sessions[uid]["job_cache"][int(idx)]
        
        bot.answer_callback_query(call.id, get_txt(uid, "ai_loading"))
        
        if prefix == "eli": # Check Eligibility
            resp = get_ai_response("eligibility", job["raw_text"], user_sessions[uid])
            bot.send_message(uid, f"👤 *Eligibility Check:*\n\n{resp}", parse_mode="Markdown")
            
        elif prefix == "sum": # Full Summary
            resp = get_ai_response("summary", job["raw_text"], user_sessions[uid])
            bot.send_message(uid, f"📝 *Job Summary:*\n\n{resp}", parse_mode="Markdown")
            
    except Exception as e:
        log_msg(f"CB Error: {e}")
        bot.answer_callback_query(call.id, get_txt(uid, "ai_error"))

if __name__ == "__main__":
    t = threading.Thread(target=bot.infinity_polling)
    t.start()
    server.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
