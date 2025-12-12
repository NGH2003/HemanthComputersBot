import os
import json
import requests
import feedparser
import pdfplumber
from bs4 import BeautifulSoup
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"

# --- VOICE SEARCH (New) ---
def transcribe_audio(audio_bytes):
    """Uses Groq Whisper to transcribe Kannada/English audio"""
    try:
        # Groq's transcription API
        transcription = client.audio.transcriptions.create(
            file=("voice.mp3", audio_bytes), # Groq handles raw bytes if named correctly
            model="whisper-large-v3",
            response_format="json",
            language="en" # Or auto-detect
        )
        return transcription.text
    except Exception as e:
        print(f"Audio Error: {e}")
        return ""

# --- (Keep existing functions: fetch_rss_feeds, fetch_url_text, extract_text_from_pdf, analyze_notification, generate_daily_quiz_content, generate_poster_prompt) ---
# ... [PASTE YOUR EXISTING AI FUNCTIONS HERE] ...
def fetch_rss_feeds(feed_urls):
    found_items = []
    for url in feed_urls:
        try:
            f = feedparser.parse(url)
            for entry in f.entries[:5]: 
                found_items.append({"title": entry.title, "link": entry.link, "summary": getattr(entry, 'summary', 'No summary'), "published": getattr(entry, 'published', 'Today')})
        except: continue
    return found_items

def fetch_url_text(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.content, 'html.parser')
        for script in soup(["script", "style"]): script.extract()
        return soup.get_text()[:10000] 
    except: return ""

def extract_text_from_pdf(pdf_file):
    try:
        with pdfplumber.open(pdf_file) as pdf:
            text = ""
            for page in pdf.pages[:3]: 
                extracted = page.extract_text()
                if extracted: text += extracted + "\n"
        return text
    except: return ""

def analyze_notification(raw_text, mode="JOB"):
    api_key = os.environ.get("GROQ_API_KEY")
    prompt = f"Analyze this text ({mode}) and return JSON: title, summary, min_age, max_age, qualification, last_date (YYYY-MM-DD), apply_link, documents. Text: {raw_text[:8000]}"
    try:
        chat = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model=MODEL_NAME, response_format={"type": "json_object"})
        return json.loads(chat.choices[0].message.content)
    except: return {}

def generate_daily_quiz_content(topic):
    prompt = f"Generate 1 GK multiple-choice question on {topic}. Return JSON: {{ 'question': '...', 'options': ['A', 'B', 'C', 'D'], 'correct_option': 'A' }}"
    try:
        chat = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model=MODEL_NAME, response_format={"type": "json_object"})
        return json.loads(chat.choices[0].message.content)
    except: return None

def generate_poster_prompt(job_title, qualification):
    prompt = f"Write a text-to-image prompt for a poster: '{job_title}'. Qual: {qualification}. Style: Gold/Black, Professional."
    try:
        chat = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model=MODEL_NAME)
        return chat.choices[0].message.content
    except: return "Error"
