import telebot
from telebot import types
import feedparser
import urllib.parse
import re
import os
import requests
import json
import datetime
from flask import Flask, request, render_template_string, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from functools import wraps
from bs4 import BeautifulSoup

# --- 1. CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8300070205:AAF3kfF2P_bSMtnJTc8uJC2waq9d2iRm0i0")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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") 
HEMANTH_WHATSAPP_NUMBER = "918970913832"
ADMIN_PASSWORD = "hemanth_admin"
SECRET_KEY = "super_secret_key"

# Database Config (Uses SQLite for simplicity, can switch to Postgres)
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'bot.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# --- 2. DATABASE MODELS (Feature #3 & #8) ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String(50), unique=True, nullable=False)
    username = db.Column(db.String(100))
    joined_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    # Preferences can be stored as JSON
    preferences = db.Column(db.Text, default="{}") 

class Source(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), unique=True, nullable=False)
    name = db.Column(db.String(100))
    last_fetched = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300))
    company = db.Column(db.String(200))
    url = db.Column(db.String(500), unique=True) # Deduping via URL
    summary = db.Column(db.Text)
    raw_desc = db.Column(db.Text)
    posted_date = db.Column(db.String(50))
    ai_analysis = db.Column(db.Text) # JSON String from Groq
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

# Create Tables
with app.app_context():
    db.create_all()
    # Add Default Feed if empty
    if not Source.query.first():
        db.session.add(Source(url="https://www.karnatakacareers.org/feed/", name="Karnataka Careers"))
        db.session.commit()

# --- 3. AI ENGINE (GROQ) (Feature #5) ---
def get_ai_analysis_json(job_text):
    """
    Forces Groq to return STRUCTURED JSON data for better filtering.
    """
    try:
        system_prompt = "You are a Job Data Extractor. Output ONLY valid JSON."
        user_prompt = (
            f"Analyze this job:\n{job_text[:3000]}\n\n"
            f"Return JSON with these keys:\n"
            f"1. 'role': Job Title\n"
            f"2. 'experience_years': Number (or 0 if fresher)\n"
            f"3. 'skills': List of strings\n"
            f"4. 'deadline': Date or 'Not Mentioned'\n"
            f"5. 'summary': 2 line summary\n"
        )

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        data = {
            "model": "llama3-8b-8192",
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            "temperature": 0.2,
            "response_format": {"type": "json_object"} # Force JSON
        }

        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        return None
    except Exception as e:
        print(f"AI Error: {e}")
        return None

# --- 4. INGESTION WORKER (Feature #2 & #9) ---
def fetch_feeds():
    """Background task to fetch RSS feeds and save new jobs to DB"""
    with app.app_context():
        sources = Source.query.filter_by(is_active=True).all()
        print(f"🔄 Scheduler: Checking {len(sources)} sources...")
        
        for source in sources:
            try:
                feed = feedparser.parse(source.url)
                for entry in feed.entries:
                    # Check if job exists (Deduplication Feature)
                    if not Job.query.filter_by(url=entry.link).first():
                        # Clean HTML
                        soup = BeautifulSoup(entry.description, "html.parser")
                        clean_text = soup.get_text(separator="\n")
                        
                        new_job = Job(
                            title=entry.title,
                            url=entry.link,
                            raw_desc=clean_text,
                            posted_date=datetime.datetime.now().strftime("%Y-%m-%d"),
                            ai_analysis="{}" # Placeholder, calculated on demand
                        )
                        db.session.add(new_job)
                        print(f"✅ New Job Found: {entry.title}")
                
                source.last_fetched = datetime.datetime.utcnow()
                db.session.commit()
            except Exception as e:
                print(f"Error fetching {source.url}: {e}")

# Start Scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=fetch_feeds, trigger="interval", minutes=30)
scheduler.start()

# --- 5. ADMIN PANEL (Feature #7) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>HC Bot Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<nav class="navbar navbar-dark bg-primary mb-4">
  <div class="container"><span class="navbar-brand">🤖 HC Bot Admin</span> <a href="/logout" class="text-white">Logout</a></div>
</nav>

<div class="container">
    <div class="row mb-4">
        <div class="col-md-4"><div class="card p-3 text-center"><h3>{{ users_count }}</h3><small>Subscribers</small></div></div>
        <div class="col-md-4"><div class="card p-3 text-center"><h3>{{ jobs_count }}</h3><small>Jobs Indexed</small></div></div>
        <div class="col-md-4"><div class="card p-3 text-center"><h3>{{ source_count }}</h3><small>Active Sources</small></div></div>
    </div>

    <div class="card mb-4">
        <div class="card-header">📡 Manage Sources</div>
        <div class="card-body">
            <ul class="list-group mb-3">
                {% for source in sources %}
                <li class="list-group-item d-flex justify-content-between">
                    <div><strong>{{ source.name }}</strong><br><small class="text-muted">{{ source.url }}</small></div>
                    <a href="/delete_source/{{ source.id }}" class="btn btn-sm btn-danger">Remove</a>
                </li>
                {% endfor %}
            </ul>
            <form action="/add_source" method="post" class="d-flex gap-2">
                <input type="text" name="name" class="form-control" placeholder="Source Name (e.g. FreeJobAlert)" required>
                <input type="text" name="url" class="form-control" placeholder="RSS URL" required>
                <button type="submit" class="btn btn-success">Add Source</button>
            </form>
        </div>
    </div>

    <div class="card">
        <div class="card-header">📄 Recent Jobs (Last 10)</div>
        <div class="card-body">
            <table class="table table-striped">
                <thead><tr><th>Title</th><th>Date</th><th>Action</th></tr></thead>
                <tbody>
                {% for job in jobs %}
                <tr>
                    <td>{{ job.title }}</td>
                    <td>{{ job.posted_date }}</td>
                    <td><a href="{{ job.url }}" target="_blank" class="btn btn-sm btn-outline-primary">View</a></td>
                </tr>
                {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
</body></html>
"""

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'): return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect('/admin')
    return '<form method="post"><input type="password" name="password"><button>Login</button></form>'

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/admin')
@login_required
def admin():
    return render_template_string(HTML_TEMPLATE,
        users_count=User.query.count(),
        jobs_count=Job.query.count(),
        source_count=Source.query.count(),
        sources=Source.query.all(),
        jobs=Job.query.order_by(Job.id.desc()).limit(10).all()
    )

@app.route('/add_source', methods=['POST'])
@login_required
def add_source():
    name = request.form.get('name')
    url = request.form.get('url')
    if url:
        db.session.add(Source(name=name, url=url))
        db.session.commit()
    return redirect('/admin')

@app.route('/delete_source/<int:id>')
@login_required
def delete_source(id):
    src = Source.query.get(id)
    if src:
        db.session.delete(src)
        db.session.commit()
    return redirect('/admin')

@app.route('/')
def home(): return redirect('/login')

# --- 6. TELEGRAM BOT LOGIC ---
user_sessions = {}

@bot.message_handler(commands=['start', 'hi'])
def send_welcome(message):
    # Register User in DB
    chat_id = str(message.chat.id)
    with app.app_context():
        if not User.query.filter_by(chat_id=chat_id).first():
            db.session.add(User(chat_id=chat_id, username=message.from_user.username))
            db.session.commit()

    user_sessions[message.chat.id] = {"filters": []}
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("SSLC", "PUC", "Diploma", "BE/B.Tech", "Degree", "Any Qualification")
    
    bot.send_message(message.chat.id, "👋 *Welcome to HC Job Bot (Pro)*\n\nI am connected to a live database.\nSelect Qualification:", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_district)

# (Reusing your filter logic, simplified for brevity)
def ask_district(message):
    if message.text != "Any Qualification": user_sessions[message.chat.id]["filters"].append(message.text)
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("Bangalore", "Mysore", "Belagavi", "Any District")
    bot.send_message(message.chat.id, "📍 District:", reply_markup=markup)
    bot.register_next_step_handler(message, show_results)

def show_results(message):
    user_id = message.chat.id
    # Logic to fetch from DB matches would go here
    # For now, we search the RSS like before, but utilizing Groq JSON in background
    bot.send_message(user_id, "🔍 Searching our Live Database...")
    
    # We fetch the latest 5 jobs from DB
    with app.app_context():
        jobs = Job.query.order_by(Job.id.desc()).limit(5).all()
        
        if not jobs:
            bot.send_message(user_id, "No jobs in database yet. Admin is ingesting...")
            return

        for job in jobs:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✨ AI Analysis", callback_data=f"ai_{job.id}"))
            
            # WhatsApp Link
            msg = f"Hi Hemanth, apply for {job.title}"
            wa_link = f"https://wa.me/{HEMANTH_WHATSAPP_NUMBER}?text={urllib.parse.quote(msg)}"
            markup.add(types.InlineKeyboardButton("📩 Apply", url=wa_link))

            bot.send_message(user_id, f"🔹 *{job.title}*\nPosted: {job.posted_date}", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ai_'))
def handle_ai(call):
    job_id = call.data.split("_")[1]
    with app.app_context():
        job = Job.query.get(job_id)
        if job:
            bot.answer_callback_query(call.id, "🤖 Generating Analysis...")
            
            # Check if we already have analysis in DB
            if not job.ai_analysis or job.ai_analysis == "{}":
                analysis_json = get_ai_analysis_json(job.raw_desc)
                job.ai_analysis = analysis_json if analysis_json else "{}"
                db.session.commit()
            
            # Parse JSON to pretty text
            try:
                data = json.loads(job.ai_analysis)
                summary = (
                    f"🤖 *AI Insight (Groq)*\n\n"
                    f"📌 *Role:* {data.get('role', 'N/A')}\n"
                    f"🎓 *Exp:* {data.get('experience_years', 0)} Years\n"
                    f"🛠 *Skills:* {', '.join(data.get('skills', []))}\n"
                    f"📝 *Summary:* {data.get('summary', 'N/A')}"
                )
                bot.send_message(call.message.chat.id, summary, parse_mode="Markdown")
            except:
                bot.send_message(call.message.chat.id, "⚠️ AI Raw Data: " + str(job.ai_analysis))

# --- 7. RUNNER ---
if __name__ == "__main__":
    # Create DB tables first
    with app.app_context():
        db.create_all()
        
    # Run Bot Thread
    import threading
    t = threading.Thread(target=bot.infinity_polling)
    t.start()
    
    # Run Flask Server
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

