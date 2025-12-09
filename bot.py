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

# Database Config
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'bot.db')
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

with app.app_context():
    db.create_all()
    if not Source.query.first():
        db.session.add(Source(url="https://www.karnatakacareers.org/feed/", name="Karnataka Careers"))
        db.session.commit()

# --- 3. IMPROVED AI ENGINE (GROQ) ---

def extract_json_from_text(text):
    """
    Cleans the AI response to ensure valid JSON.
    Removes markdown code blocks (```json ... ```).
    """
    try:
        # Find the first '{' and the last '}'
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end != -1:
            json_str = text[start:end]
            return json.loads(json_str)
        return None
    except:
        return None

def get_ai_analysis_json(job_text):
    """
    Forces Groq to return STRUCTURED JSON data.
    """
    try:
        # 1. Clean the job text to remove massive HTML mess
        clean_job_text = job_text[:4000].replace('"', "'") 

        system_prompt = "You are a Job Data API. You only output valid JSON. No conversational text."
        
        # 2. Strict User Prompt with Example
        user_prompt = (
            f"Analyze this job description and return a JSON object.\n\n"
            f"JOB DESCRIPTION:\n{clean_job_text}\n\n"
            f"REQUIRED JSON FORMAT:\n"
            f"{{\n"
            f'  "role": "Job Title",\n'
            f'  "exp": "0-1 Years" (or "0" if fresher),\n'
            f'  "skills": ["Skill1", "Skill2"],\n'
            f'  "summary": "Short 2-line summary of eligibility"\n'
            f"}}\n\n"
            f"If information is missing, use 'Not Mentioned'. Do not make things up."
        )

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        data = {
            "model": "llama3-8b-8192",
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            "temperature": 0.1 # Low temperature = More precise
        }

        print("🤖 Sending request to Groq...") # Log to Render
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            raw_text = response.json()['choices'][0]['message']['content']
            print(f"✅ Groq Raw Response: {raw_text}") # Debug Log
            
            # Clean and Parse
            parsed_json = extract_json_from_text(raw_text)
            if parsed_json:
                return json.dumps(parsed_json) # Return as string for DB
            else:
                print("❌ Failed to parse JSON from AI")
                return None
        else:
            print(f"❌ Groq Error: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Critical AI Error: {e}")
        return None

# --- 4. INGESTION WORKER ---
def fetch_feeds():
    with app.app_context():
        sources = Source.query.filter_by(is_active=True).all()
        for source in sources:
            try:
                feed = feedparser.parse(source.url)
                for entry in feed.entries:
                    if not Job.query.filter_by(url=entry.link).first():
                        soup = BeautifulSoup(entry.description, "html.parser")
                        clean_text = soup.get_text(separator="\n")
                        
                        new_job = Job(
                            title=entry.title,
                            url=entry.link,
                            raw_desc=clean_text,
                            posted_date=datetime.datetime.now().strftime("%Y-%m-%d"),
                            ai_analysis="" # Empty initially
                        )
                        db.session.add(new_job)
                        print(f"✅ New Job: {entry.title}")
                source.last_fetched = datetime.datetime.utcnow()
                db.session.commit()
            except Exception as e:
                print(f"Feed Error: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(func=fetch_feeds, trigger="interval", minutes=30)
scheduler.start()

# --- 5. ADMIN PANEL ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><title>HC Admin</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head>
<body class="bg-light p-4">
    <h2>🤖 HC Bot Admin</h2>
    <div class="row mb-4">
        <div class="col-md-4"><div class="card p-3"><h3>{{ users }}</h3><small>Users</small></div></div>
        <div class="col-md-4"><div class="card p-3"><h3>{{ jobs }}</h3><small>Jobs</small></div></div>
    </div>
    <div class="card">
        <div class="card-header">Manage Sources</div>
        <div class="card-body">
            <ul class="list-group mb-3">
                {% for s in sources %}
                <li class="list-group-item d-flex justify-content-between">{{ s.name }} <a href="/del/{{ s.id }}" class="btn btn-sm btn-danger">X</a></li>
                {% endfor %}
            </ul>
            <form action="/add" method="post" class="d-flex"><input name="url" class="form-control" placeholder="URL"><button class="btn btn-success">Add</button></form>
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

@app.route('/admin')
@login_required
def admin():
    return render_template_string(HTML_TEMPLATE, users=User.query.count(), jobs=Job.query.count(), sources=Source.query.all())

@app.route('/add', methods=['POST'])
@login_required
def add():
    if request.form.get('url'): db.session.add(Source(url=request.form.get('url'), name="New Feed")); db.session.commit()
    return redirect('/admin')

@app.route('/del/<int:id>')
@login_required
def delete(id):
    s = Source.query.get(id); db.session.delete(s); db.session.commit()
    return redirect('/admin')

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
    bot.send_message(message.chat.id, "👋 *Welcome to HC Job Bot*\n\nSelect Qualification:", parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(message, ask_district)

def ask_district(message):
    user_sessions[message.chat.id] = {"filters": [message.text]}
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add("Bangalore", "Mysore", "Belagavi", "Any District")
    bot.send_message(message.chat.id, "📍 Select District:", reply_markup=markup)
    bot.register_next_step_handler(message, show_results)

def show_results(message):
    user_id = message.chat.id
    bot.send_message(user_id, "🔍 Searching Live Database...")
    
    with app.app_context():
        # Get 5 latest jobs
        jobs = Job.query.order_by(Job.id.desc()).limit(5).all()
        
        if not jobs:
            bot.send_message(user_id, "⚠️ No jobs found in database yet. Wait for ingestion.")
            return

        for job in jobs:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✨ AI Insight", callback_data=f"ai_{job.id}"))
            
            wa_link = f"https://wa.me/{HEMANTH_WHATSAPP_NUMBER}?text={urllib.parse.quote(f'Hi Hemanth, apply for {job.title}')}"
            markup.add(types.InlineKeyboardButton("📩 Apply", url=wa_link))

            bot.send_message(user_id, f"🔹 *{job.title}*\n📅 {job.posted_date}", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ai_'))
def handle_ai(call):
    job_id = call.data.split("_")[1]
    with app.app_context():
        job = Job.query.get(job_id)
        if job:
            bot.answer_callback_query(call.id, "🤖 Generating Analysis...")
            
            # If no analysis exists, fetch it
            if not job.ai_analysis or len(job.ai_analysis) < 5:
                analysis = get_ai_analysis_json(job.raw_desc)
                if analysis:
                    job.ai_analysis = analysis
                    db.session.commit()
                else:
                    bot.send_message(call.message.chat.id, "⚠️ AI could not read this job. Please check the official link.")
                    return

            # Display Analysis
            try:
                data = json.loads(job.ai_analysis)
                
                # Check if data is empty or N/A
                role = data.get('role', 'N/A')
                exp = data.get('exp', 'N/A')
                skills = data.get('skills', [])
                summary = data.get('summary', 'N/A')
                
                if isinstance(skills, list):
                    skills_txt = ", ".join(skills)
                else:
                    skills_txt = str(skills)

                msg = (
                    f"🤖 *AI Insight (Groq)*\n\n"
                    f"📌 *Role:* {role}\n"
                    f"🎓 *Exp:* {exp}\n"
                    f"🛠 *Skills:* {skills_txt}\n"
                    f"📝 *Summary:* {summary}"
                )
                bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")
            except Exception as e:
                bot.send_message(call.message.chat.id, f"⚠️ Error parsing AI data: {str(e)}")

if __name__ == "__main__":
    import threading
    with app.app_context():
        db.create_all()
    t = threading.Thread(target=bot.infinity_polling)
    t.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
