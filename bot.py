import telebot
from telebot import types
import feedparser
import urllib.parse
import re
import os
import requests
from flask import Flask, request, render_template_string, redirect, url_for, session, flash
import threading
from bs4 import BeautifulSoup
import google.generativeai as genai
from functools import wraps
import datetime

# --- 1. CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8300070205:AAF3kfF2P_bSMtnJTc8uJC2waq9d2iRm0i0")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyDA-0mch6ZRr9eARG97bYunAATQQ81gb8k")
HEMANTH_WHATSAPP_NUMBER = "918970913832"
ADMIN_PASSWORD = "hemanth_admin"  # <--- PASSWORD FOR ADMIN PANEL
SECRET_KEY = "super_secret_key"   # Needed for login session

# Default Feeds
DEFAULT_FEEDS = ["https://www.karnatakacareers.org/feed/"]

# In-Memory Storage (Resets if server restarts on Free Tier)
app_data = {
    "rss_feeds": DEFAULT_FEEDS,
    "total_users": set(),
    "requests_count": 0,
    "logs": []
}

# Initialize AI & Bot
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
server = Flask(__name__)
server.secret_key = SECRET_KEY

# --- 2. LOGGING HELPER ---
def log_msg(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {message}"
    print(entry)
    app_data["logs"].insert(0, entry) # Add to top
    if len(app_data["logs"]) > 50: app_data["logs"].pop() # Keep last 50

# --- 3. AI & JOB FUNCTIONS ---

def clean_html(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    return soup.get_text(separator="\n")

def get_personalized_summary(job_text, user_age, user_qual):
    try:
        age_txt = user_age if user_age and user_age.isdigit() else "Not Provided"
        qual_txt = user_qual if user_qual else "Not Provided"
        prompt = (
            f"Compare User Profile with Job.\n"
            f"User: Age {age_txt}, Qual {qual_txt}\n"
            f"Job: {job_text[:2000]}\n"
            f"Task: 1. Eligibility Verdict (Yes/No/Maybe). 2. Short Summary."
        )
        response = model.generate_content(prompt)
        app_data["requests_count"] += 1
        return response.text
    except Exception as e:
        log_msg(f"AI Error: {e}")
        return "⚠️ AI Busy."

def get_job_details(filters, age_limit):
    matches = []
    log_msg(f"Searching feeds for: {filters}")
    
    for feed_url in app_data["rss_feeds"]:
        try:
            # Smart Search URL construction
            search_terms = [f for f in filters if "Any" not in f]
            if search_terms:
                safe_query = urllib.parse.quote(" ".join(search_terms))
                final_url = f"{feed_url}?s={safe_query}"
            else:
                final_url = feed_url # Show latest if no filters
                
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

# --- 4. ADMIN PANEL (WEB INTERFACE) ---

# HTML Template (Single file for simplicity)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Hemanth Bot Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body{background:#f8f9fa;} .card{margin-bottom:20px; box-shadow:0 2px 4px rgba(0,0,0,0.1);}</style>
</head>
<body>
<nav class="navbar navbar-dark bg-primary mb-4">
  <div class="container">
    <span class="navbar-brand mb-0 h1">🤖 Hemanth Bot Admin</span>
    <a href="/logout" class="btn btn-sm btn-light">Logout</a>
  </div>
</nav>

<div class="container">
    <div class="row">
        <div class="col-md-4">
            <div class="card text-center p-3">
                <h3>{{ users_count }}</h3>
                <small class="text-muted">Total Users</small>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card text-center p-3">
                <h3>{{ request_count }}</h3>
                <small class="text-muted">AI Requests</small>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card text-center p-3">
                <h3>{{ feed_count }}</h3>
                <small class="text-muted">Active Feeds</small>
            </div>
        </div>
    </div>

    <div class="card">
        <div class="card-header bg-white"><strong>📡 Manage RSS Feeds</strong></div>
        <div class="card-body">
            <ul class="list-group mb-3">
                {% for feed in feeds %}
                <li class="list-group-item d-flex justify-content-between align-items-center">
                    {{ feed }}
                    <a href="/delete_feed?url={{ feed }}" class="btn btn-sm btn-danger">❌</a>
                </li>
                {% endfor %}
            </ul>
            <form action="/add_feed" method="post" class="d-flex">
                <input type="text" name="url" class="form-control me-2" placeholder="https://example.com/feed/" required>
                <button type="submit" class="btn btn-success">Add Feed</button>
            </form>
        </div>
    </div>

    <div class="card">
        <div class="card-header bg-white"><strong>📜 Live Logs</strong></div>
        <div class="card-body bg-dark text-white" style="height:300px; overflow-y:scroll; font-family:monospace; font-size:12px;">
            {% for log in logs %}
            <div>{{ log }}</div>
            {% endfor %}
        </div>
    </div>
</div>
</body>
</html>
"""

LOGIN_HTML = """
<div style="display:flex; justify-content:center; align-items:center; height:100vh; background:#f0f2f5;">
    <form method="post" style="background:white; padding:30px; border-radius:10px; box-shadow:0 4px 6px rgba(0,0,0,0.1);">
        <h3 style="margin-bottom:20px;">🔒 Admin Login</h3>
        <input type="password" name="password" placeholder="Enter Admin Password" style="width:100%; padding:10px; margin-bottom:10px; border:1px solid #ddd; border-radius:5px;">
        <button type="submit" style="width:100%; padding:10px; background:#007bff; color:white; border:none; border-radius:5px; cursor:pointer;">Login</button>
    </form>
</div>
"""

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect('/login')
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
    return render_template_string(HTML_TEMPLATE, 
        users_count=len(app_data["total_users"]),
        request_count=app_data["requests_count"],
        feed_count=len(app_data["rss_feeds"]),
        feeds=app_data["rss_feeds"],
        logs=app_data["logs"]
    )

@server.route('/add_feed', methods=['POST'])
@login_required
def add_feed():
    url = request.form.get('url')
    if url and url not in app_data["rss_feeds"]:
        app_data["rss_feeds"].append(url)
        log_msg(f"Admin added feed: {url}")
    return redirect('/admin')

@server.route('/delete_feed')
@login_required
def delete_feed():
    url = request.args.get('url')
    if url in app_data["rss_feeds"]:
        app_data["rss_feeds"].remove(url)
        log_msg(f"Admin removed feed: {url}")
    return redirect('/admin')

@server.route('/')
def home():
    return redirect('/login')

# --- 5. TELEGRAM HANDLERS (Same as before) ---
# ... (User logic remains mostly the same, just logging added) ...
user_sessions = {}

@bot.message_handler(commands=['start', 'hi'])
def send_welcome(message):
    app_data["total_users"].add(message.chat.id) # Track user
    log_msg(f"User {message.chat.id} started bot")
    
    user_sessions[message.chat.id] = {"filters": []}
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("SSLC", "PUC", "Diploma", "BE/B.Tech", "Degree", "Any Qualification")
    bot.send_message(message.chat.id, "👋 *Hemanth Bot*\nSelect Qualification:", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_district)

def ask_district(message):
    if message.text not in ["Any Qualification", "Any"]: 
        user_sessions[message.chat.id]["filters"].append(message.text)
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("Bangalore", "Mysore", "Belagavi", "Tumkur", "All Karnataka", "Any District")
    bot.send_message(message.chat.id, "📍 Select **District**:", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_department)

def ask_department(message):
    if message.text not in ["Any District", "Skip"]: 
        user_sessions[message.chat.id]["filters"].append(message.text)
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("Health", "Police", "Railway", "KPSC", "Court", "Any Department")
    bot.send_message(message.chat.id, "🏢 Which **Department**?", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_age)

def ask_age(message):
    if message.text not in ["Any Department", "Skip"]: 
        user_sessions[message.chat.id]["filters"].append(message.text)
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("Any Age")
    bot.send_message(message.chat.id, "🎂 Type **Age** or 'Any Age':", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, show_results)

def show_results(message):
    user_id = message.chat.id
    text = message.text
    age_check = text if text.isdigit() else None
    
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
        bot.answer_callback_query(call.id, "🤖 Analyzing...")
        summary = get_personalized_summary(job["raw_text"], "Any", "Any") # Simplify for brevity
        bot.send_message(user_id, f"🤖 *AI Analysis:*\n{summary}", parse_mode="Markdown")
    except:
        bot.answer_callback_query(call.id, "Error.")

# --- 6. RUNNER ---
if __name__ == "__main__":
    t = threading.Thread(target=bot.infinity_polling)
    t.start()
    server.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

