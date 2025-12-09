import telebot
from telebot import types
import feedparser
import urllib.parse
import re
import os
import requests # <--- We need this for the CURL-like request
import json
from flask import Flask, request, render_template_string, redirect, url_for, session
import threading
from bs4 import BeautifulSoup
from functools import wraps
import datetime

# --- 1. CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8300070205:AAF3kfF2P_bSMtnJTc8uJC2waq9d2iRm0i0")
# 🔴 Replace with your NEW API Key (Delete the old exposed one!)
GEMINI_API_KEY = "AIzaSyBCAWd0C272SY6LmMYikMqziHvncN1o8gk" 
HEMANTH_WHATSAPP_NUMBER = "918970913832"
ADMIN_PASSWORD = "hemanth_admin"
SECRET_KEY = "super_secret_key"

DEFAULT_FEEDS = ["https://www.karnatakacareers.org/feed/"]

app_data = {
    "rss_feeds": DEFAULT_FEEDS,
    "total_users": set(),
    "requests_count": 0,
    "logs": []
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

# --- 3. AI & JOB FUNCTIONS ---

def clean_html(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    return soup.get_text(separator="\n")

def get_personalized_summary(job_text, user_age, user_qual):
    """
    Uses Gemini 2.0 Flash via direct HTTP Request (Like CURL)
    """
    try:
        age_txt = user_age if user_age and user_age.isdigit() else "Not Provided"
        qual_txt = user_qual if user_qual else "Not Provided"
        
        # 1. Prepare the Prompt
        prompt_text = (
            f"Act as a Job Expert. Compare User Profile with Job.\n"
            f"User Profile: Age {age_txt}, Qualification {qual_txt}\n"
            f"Job Notification: {job_text[:3000]}\n"
            f"Task:\n"
            f"1. Start with '✅ Eligible', '❌ Not Eligible', or '⚠️ Check details'.\n"
            f"2. Explain why in 1 short sentence.\n"
            f"3. List: Role, Posts, Age Limit, Last Date."
        )

        # 2. The URL (Gemini 2.0 Flash)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        
        # 3. The Payload (JSON Data)
        headers = {'Content-Type': 'application/json'}
        data = {
            "contents": [{
                "parts": [{"text": prompt_text}]
            }]
        }

        # 4. Send Request (This is the Python version of CURL)
        response = requests.post(url, headers=headers, json=data)
        
        # 5. Handle Response
        if response.status_code == 200:
            result = response.json()
            # Extract text from complex JSON structure
            ai_text = result['candidates'][0]['content']['parts'][0]['text']
            app_data["requests_count"] += 1
            return ai_text
        else:
            log_msg(f"AI Error {response.status_code}: {response.text}")
            return f"⚠️ AI Error: Server returned {response.status_code}"

    except Exception as e:
        log_msg(f"Connection Error: {e}")
        return "⚠️ AI Service Busy."

def get_job_details(filters, age_limit):
    matches = []
    log_msg(f"Searching feeds for: {filters}")
    
    for feed_url in app_data["rss_feeds"]:
        try:
            search_terms = [f for f in filters if "Any" not in f]
            if search_terms:
                safe_query = urllib.parse.quote(" ".join(search_terms))
                final_url = f"{feed_url}?s={safe_query}"
            else:
                final_url = feed_url 
                
            feed = feedparser.parse(final_url)
            for entry in feed.entries:
                content = (entry.title + " " + entry.description).lower()
                
                if age_limit and age_limit.isdigit():
                    age_match = re.search(r'(\d{2})\s*(?:-|to)\s*(\d{2})', content)
                    if age_match:
                        min_age, max_age = map(int, age_match.groups())
                        if not (min_age <= int(age_limit) <= max_age):
                            continue 

                posts_match = re.search(r'(?:total|no\. of)\s*(?:posts|vacancies)\s*[:\-]?\s*(\d+)', content, re.IGNORECASE)
                total_posts = posts_match.group(1) if posts_match else "View"
                
                date_match = re.search(r'last\s*date\s*[:\-]?\s*(\d{2}[-./]\d{2}[-./]\d{4})', content, re.IGNORECASE)
                last_date = date_match.group(1) if date_match else "Check Link"

                msg_text = f"Hi Hemanth, apply for *{entry.title}*."
                wa_link = f"https://wa.me/{HEMANTH_WHATSAPP_NUMBER}?text={urllib.parse.quote(msg_text)}"

                matches.append({
                    "title": entry.title,
                    "posts": total_posts,
                    "date": last_date,
                    "link": wa_link,
                    "raw_text": clean_html(entry.description),
                    "id": len(matches)
                })
                if len(matches) >= 5: break
        except Exception as e:
            log_msg(f"Feed Error ({feed_url}): {e}")
            continue
    return matches

# --- 4. ADMIN PANEL ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Hemanth Bot Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>
<nav class="navbar navbar-dark bg-primary mb-4">
  <div class="container"><span class="navbar-brand mb-0 h1">🤖 Hemanth Bot Admin</span></div>
</nav>
<div class="container">
    <div class="row">
        <div class="col-md-4"><div class="card p-3 mb-2"><h3>{{ users_count }}</h3><small>Users</small></div></div>
        <div class="col-md-4"><div class="card p-3 mb-2"><h3>{{ request_count }}</h3><small>AI Requests</small></div></div>
        <div class="col-md-4"><div class="card p-3 mb-2"><h3>{{ feed_count }}</h3><small>Feeds</small></div></div>
    </div>
    <div class="card mb-3">
        <div class="card-header">Manage Feeds</div>
        <div class="card-body">
            <ul class="list-group mb-3">
                {% for feed in feeds %}
                <li class="list-group-item d-flex justify-content-between">{{ feed }} <a href="/delete_feed?url={{ feed }}" class="btn btn-sm btn-danger">X</a></li>
                {% endfor %}
            </ul>
            <form action="/add_feed" method="post" class="d-flex">
                <input type="text" name="url" class="form-control me-2" required>
                <button type="submit" class="btn btn-success">Add</button>
            </form>
        </div>
    </div>
    <div class="card">
        <div class="card-header">Logs</div>
        <div class="card-body bg-dark text-white" style="height:300px; overflow-y:scroll; font-size:12px;">
            {% for log in logs %}<div>{{ log }}</div>{% endfor %}
        </div>
    </div>
</div>
</body></html>
"""

LOGIN_HTML = """
<div style="height:100vh; display:flex; justify-content:center; align-items:center;">
    <form method="post" style="padding:20px; border:1px solid #ccc;">
        <h3>Login</h3><input type="password" name="password"><button>Login</button>
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

@server.route('/admin')
@login_required
def admin_panel():
    return render_template_string(HTML_TEMPLATE, users_count=len(app_data["total_users"]), request_count=app_data["requests_count"], feed_count=len(app_data["rss_feeds"]), feeds=app_data["rss_feeds"], logs=app_data["logs"])

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

@bot.message_handler(commands=['start', 'hi'])
def send_welcome(message):
    app_data["total_users"].add(message.chat.id)
    user_sessions[message.chat.id] = {"filters": []}
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("SSLC", "PUC", "Diploma", "BE/B.Tech", "Degree", "Any Qualification")
    bot.send_message(message.chat.id, "👋 *Hemanth Bot*\nSelect Qualification:", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_district)

def ask_district(message):
    if message.text not in ["Any Qualification", "Any"]: user_sessions[message.chat.id]["filters"].append(message.text)
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("Bangalore", "Mysore", "Belagavi", "Tumkur", "All Karnataka", "Any District")
    bot.send_message(message.chat.id, "📍 Select **District**:", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_department)

def ask_department(message):
    if message.text not in ["Any District", "Skip"]: user_sessions[message.chat.id]["filters"].append(message.text)
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("Health", "Police", "Railway", "KPSC", "Court", "Any Department")
    bot.send_message(message.chat.id, "🏢 Which **Department**?", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_age)

def ask_age(message):
    if message.text not in ["Any Department", "Skip"]: user_sessions[message.chat.id]["filters"].append(message.text)
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("Any Age")
    bot.send_message(message.chat.id, "🎂 Type **Age** or 'Any Age':", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, show_results)

def show_results(message):
    user_id = message.chat.id
    text = message.text
    age_check = text if text.isdigit() else None
    
    # Save Age and Qualification for AI Context
    user_sessions[user_id]["age"] = age_check if age_check else "Any"
    # Try to find qualification in filters
    qual = "Any"
    for f in user_sessions[user_id]["filters"]:
        if f in ["SSLC", "PUC", "Diploma", "BE/B.Tech", "Degree"]: qual = f
    user_sessions[user_id]["qual"] = qual
    
    bot.send_message(user_id, "🔍 Searching...")
    jobs = get_job_details(user_sessions[user_id]["filters"], age_check)
    user_sessions[user_id]["job_cache"] = jobs
    
    if not jobs:
        bot.send_message(user_id, "❌ No jobs found.")
    else:
        for i, job in enumerate(jobs):
            markup = types.InlineKeyboardMarkup()
            markup.row(
                types.InlineKeyboardButton("📩 Apply", url=job['link']),
                types.InlineKeyboardButton("✨ Check Eligibility", callback_data=f"ai_{i}")
            )
            bot.send_message(user_id, f"🔹 *{job['title']}*\nVacancies: {job['posts']}", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ai_'))
def handle_ai(call):
    user_id = call.message.chat.id
    idx = int(call.data.split("_")[1])
    try:
        job = user_sessions[user_id]["job_cache"][idx]
        u_age = user_sessions[user_id].get("age", "Not Provided")
        u_qual = user_sessions[user_id].get("qual", "Not Provided")
        
        bot.answer_callback_query(call.id, "🤖 AI Checking Eligibility...")
        summary = get_personalized_summary(job["raw_text"], u_age, u_qual)
        bot.send_message(user_id, f"🤖 *AI Analysis (Gemini 2.0 Flash):*\n{summary}", parse_mode="Markdown")
    except Exception as e:
        log_msg(f"Callback Error: {e}")
        bot.answer_callback_query(call.id, "Error.")

if __name__ == "__main__":
    t = threading.Thread(target=bot.infinity_polling)
    t.start()
    server.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
