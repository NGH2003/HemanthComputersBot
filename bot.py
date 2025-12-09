import telebot
from telebot import types
import feedparser
import urllib.parse
import re
import os
import requests
import json
import datetime
import threading
from flask import Flask, request, render_template_string, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from functools import wraps
from bs4 import BeautifulSoup

# --- 1. CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "YOUR_GROQ_API_KEY") 
HEMANTH_WHATSAPP_NUMBER = "918970913832"
ADMIN_PASSWORD = "hemanth_admin"
SECRET_KEY = "super_secret_key"

# Database Config
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.secret_key = SECRET_KEY

# 🔴 YOUR DATABASE URL IS HERE (Correctly formatted with quotes)
database_url = "postgresql://postgres:Ngh%402003@db.drvivmkgypzxfcwarqav.supabase.co:5432/postgres"

# Fix for SQLAlchemy format (postgres:// -> postgresql://)
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# --- 2. DATABASE MODELS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String(50), unique=True, nullable=False)
    username = db.Column(db.String(100))
    joined_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Source(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), unique=True, nullable=False)
    name = db.Column(db.String(100))
    last_fetched = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300))
    url = db.Column(db.String(500), unique=True)
    raw_desc = db.Column(db.Text)
    posted_date = db.Column(db.String(50))
    ai_analysis = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

# Create Tables & Default Feed
with app.app_context():
    db.create_all()
    if not Source.query.first():
        db.session.add(Source(url="https://www.karnatakacareers.org/feed/", name="Karnataka Careers"))
        db.session.commit()

# --- 3. AI ENGINE (GROQ) ---
def extract_json_from_text(text):
    try:
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end != -1:
            return json.loads(text[start:end])
        return None
    except: return None

def get_ai_analysis_json(job_text):
    try:
        clean_job_text = job_text[:3500].replace('"', "'") 
        system_prompt = "You are a Job Data API. Output valid JSON only."
        user_prompt = (
            f"Analyze job and return JSON:\n{clean_job_text}\n\n"
            f"REQUIRED JSON FORMAT:\n"
            f"{{\n"
            f'  "role": "Job Title",\n'
            f'  "exp": "0-1 Years" (or "0" if fresher),\n'
            f'  "skills": ["Skill1", "Skill2"],\n'
            f'  "summary": "Short 2-line summary of eligibility"\n'
            f"}}"
        )
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        data = {
            "model": "llama3-8b-8192",
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            "temperature": 0.1
        }
        
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            raw = response.json()['choices'][0]['message']['content']
            parsed = extract_json_from_text(raw)
            return json.dumps(parsed) if parsed else None
        else:
            print(f"Groq Error: {response.text}")
            return None
    except Exception as e:
        print(f"AI Error: {e}")
        return None

# --- 4. INGESTION WORKER ---
def fetch_feeds():
    with app.app_context():
        sources = Source.query.filter_by(is_active=True).all()
        for source in sources:
            try:
                d = feedparser.parse(source.url, agent="Mozilla/5.0")
                for entry in d.entries:
                    if not Job.query.filter_by(url=entry.link).first():
                        # Smart Text Extraction
                        raw_html = ""
                        if 'content' in entry: raw_html = entry.content[0].value
                        elif 'summary' in entry: raw_html = entry.summary
                        elif 'description' in entry: raw_html = entry.description
                        
                        soup = BeautifulSoup(raw_html, "html.parser")
                        clean = soup.get_text(separator="\n").strip()
                        if len(clean) < 50: clean = f"Job Title: {entry.title}. Visit link for info."

                        new_job = Job(
                            title=entry.title, url=entry.link, raw_desc=clean,
                            posted_date=datetime.datetime.now().strftime("%Y-%m-%d"),
                            ai_analysis=""
                        )
                        db.session.add(new_job)
                        print(f"✅ Ingested: {entry.title}")
                source.last_fetched = datetime.datetime.utcnow()
                db.session.commit()
            except Exception as e: print(f"Feed Error {source.url}: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(func=fetch_feeds, trigger="interval", minutes=30)
scheduler.start()

# --- 5. ADMIN PANEL ---
HTML_TEMPLATE = """
<!DOCTYPE html><html><head><title>HC Admin</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head>
<body class="bg-light p-4">
    <nav class="navbar navbar-dark bg-primary mb-4 rounded px-3"><span class="navbar-brand">🤖 HC Bot Admin</span><a href="/logout" class="text-white">Logout</a></nav>
    <div class="row mb-4">
        <div class="col-md-4"><div class="card p-3"><h3>{{ users }}</h3><small>Users</small></div></div>
        <div class="col-md-4"><div class="card p-3"><h3>{{ jobs }}</h3><small>Jobs</small></div></div>
        <div class="col-md-4"><div class="card p-3"><h3>{{ sources|length }}</h3><small>Feeds</small></div></div>
    </div>
    <div class="card mb-4"><div class="card-header">Manage Sources</div><div class="card-body">
        <ul class="list-group mb-3">{% for s in sources %}<li class="list-group-item d-flex justify-content-between">{{ s.url }} <a href="/del/{{ s.id }}" class="btn btn-danger btn-sm">X</a></li>{% endfor %}</ul>
        <form action="/add" method="post" class="d-flex"><input name="url" class="form-control me-2" placeholder="RSS URL"><button class="btn btn-success">Add</button></form>
    </div></div>
    <div class="card"><div class="card-header">Actions</div><div class="card-body"><a href="/force_update" class="btn btn-warning">🔄 Force Update Feeds Now</a></div></div>
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
    return '<div style="display:flex;justify-content:center;align-items:center;height:100vh"><form method="post" style="padding:20px;border:1px solid #ccc"><h3>Login</h3><input type="password" name="password"><button>Login</button></form></div>'

@app.route('/logout')
def logout(): session.clear(); return redirect('/login')

@app.route('/admin')
@login_required
def admin(): return render_template_string(HTML_TEMPLATE, users=User.query.count(), jobs=Job.query.count(), sources=Source.query.all())

@app.route('/add', methods=['POST'])
@login_required
def add():
    if request.form.get('url'): db.session.add(Source(url=request.form.get('url'), name="New")); db.session.commit()
    return redirect('/admin')

@app.route('/del/<int:id>')
@login_required
def delete(id):
    s = Source.query.get(id); db.session.delete(s); db.session.commit()
    return redirect('/admin')

@app.route('/force_update')
@login_required
def force_update():
    t = threading.Thread(target=fetch_feeds); t.start()
    return "Update Started! Check back in 1 min. <a href='/admin'>Back</a>"

@app.route('/')
def home(): return redirect('/login')

# --- 6. TELEGRAM BOT ---
user_sessions = {}

@bot.message_handler(commands=['start', 'hi'])
def send_welcome(message):
    chat_id = str(message.chat.id)
    with app.app_context():
        if not User.query.filter_by(chat_id=chat_id).first():
            db.session.add(User(chat_id=chat_id, username=message.from_user.username))
            db.session.commit()
    
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("SSLC", "PUC", "Diploma", "BE/B.Tech", "Degree", "Any Qualification")
    
    name = message.from_user.first_name
    bot.send_message(message.chat.id, f"👋 *Hi {name}, Welcome to Hemanth Computers Bot*\n\nSelect Qualification:", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_district)

def ask_district(message):
    user_sessions[message.chat.id] = {"qual": message.text}
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("Bangalore", "Mysore", "Belagavi", "Any District")
    bot.send_message(message.chat.id, "📍 Select District:", reply_markup=markup)
    bot.register_next_step_handler(message, show_results)

def show_results(message):
    try:
        user_id = message.chat.id
        bot.send_message(user_id, "🔍 Searching Live Database...")
        
        with app.app_context():
            jobs = Job.query.order_by(Job.id.desc()).limit(5).all()
            
            if not jobs:
                bot.send_message(user_id, "⚠️ Database is updating... please wait 1 min and try again.")
                return

            for job in jobs:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("✨ AI Insight", callback_data=f"ai_{job.id}"))
                wa_link = f"https://wa.me/{HEMANTH_WHATSAPP_NUMBER}?text={urllib.parse.quote(f'Hi Hemanth, apply for {job.title}')}"
                markup.add(types.InlineKeyboardButton("📩 Apply", url=wa_link))
                
                bot.send_message(user_id, f"🔹 *{job.title}*\n📅 {job.posted_date}", parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        print(f"Error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('ai_'))
def handle_ai(call):
    try:
        job_id = call.data.split("_")[1]
        with app.app_context():
            job = Job.query.get(job_id)
            if job:
                bot.answer_callback_query(call.id, "🤖 Analyzing...")
                
                # Check update needed
                force_update = False
                if job.ai_analysis:
                    try:
                        existing = json.loads(job.ai_analysis)
                        if existing.get('role') == 'Job Title': force_update = True
                    except: force_update = True

                if not job.ai_analysis or len(job.ai_analysis) < 5 or force_update:
                    analysis = get_ai_analysis_json(job.raw_desc)
                    if analysis:
                        job.ai_analysis = analysis
                        db.session.commit()
                    else:
                        bot.send_message(call.message.chat.id, "⚠️ AI Error. Check link.")
                        return

                if job.ai_analysis and len(job.ai_analysis) > 5:
                    data = json.loads(job.ai_analysis)
                    role = data.get('role', 'N/A')
                    exp = data.get('exp', 'N/A')
                    skills_raw = data.get('skills', [])
                    skills = ", ".join(skills_raw) if isinstance(skills_raw, list) else str(skills_raw)
                    summary = data.get('summary', 'N/A')
                    msg = f"🤖 *AI Insight*\n\n📌 *Role:* {role}\n🎓 *Exp:* {exp}\n🛠 *Skills:* {skills}\n📝 *Summary:* {summary}"
                    bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")
                else:
                    bot.send_message(call.message.chat.id, "⚠️ AI returned empty data.")
    except Exception as e:
        print(f"AI Callback Error: {e}")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    
    try: bot.remove_webhook()
    except: pass

    t = threading.Thread(target=bot.infinity_polling)
    t.start()
    
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000))
