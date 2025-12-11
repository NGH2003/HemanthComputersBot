import os
import json
import requests
import feedparser
import pdfplumber
from bs4 import BeautifulSoup
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"

# --- WEB TOOLS ---
def fetch_rss_feeds():
    """Pulls latest updates from trusted sources"""
    feeds = [
        "https://kannada.oneindia.com/rss/feeds/kannada-jobs-fb.xml",
        "https://www.freejobalert.com/feed",
        "https://kannada.news18.com/commonfeeds/v1/kannada/rss/career.xml"
    ]
    found_items = []
    for url in feeds:
        try:
            f = feedparser.parse(url)
            for entry in f.entries[:5]: 
                found_items.append({
                    "title": entry.title,
                    "link": entry.link,
                    "summary": getattr(entry, 'summary', 'No summary'),
                    "published": getattr(entry, 'published', 'Today')
                })
        except: continue
    return found_items

def fetch_url_text(url):
    """Scrapes text from a website link"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.content, 'html.parser')
        for script in soup(["script", "style"]): script.extract()
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        text = '\n'.join(chunk for line in lines for chunk in line.split("  ") if chunk)
        return text[:10000] 
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

# --- AI ANALYSIS ---
def analyze_notification(raw_text, mode="JOB"):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key: return {"error": "CRITICAL: GROQ_API_KEY is missing."}

    if mode == "SCHEME":
        focus = "Extract 'Benefits' (e.g. Rs 2000) and 'Beneficiaries' (e.g. Women)."
    elif mode in ["RESULT", "KEY_ANSWER"]:
        focus = "Extract Exam Name and Result Link."
    else:
        focus = "Extract Job Title, Age, Qualification, Documents."

    prompt = f"""
    Analyze this text and return JSON ONLY.
    Context: {focus}
    
    PART 2: DETAILED ANALYTICS (Markdown Report)
    Generate a professional "Detailed Report" (Markdown) covering Highlights, Eligibility, Dates, Fees.
    
    Structure:
    {{
        "title": "Title", 
        "summary": "Short Kanglish summary", 
        "min_age": 18, "max_age": 60,
        "qualification": "Eligibility", 
        "last_date": "DD/MM/YYYY", 
        "apply_link": "URL",
        "documents": "List of docs...",
        "detailed_analysis": "Markdown report..."
    }}
    Text: {raw_text[:8000]} 
    """
    try:
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=MODEL_NAME, response_format={"type": "json_object"}
        )
        return json.loads(chat.choices[0].message.content)
    except Exception as e: return {"error": f"Groq API Failed: {str(e)}"}

def generate_daily_quiz_content(topic):
    prompt = f"""Generate 1 GK multiple-choice question on {topic}. Return JSON: {{ "question": "...", "options": ["A", "B", "C", "D"], "correct_option": "A" }}"""
    try:
        chat = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model=MODEL_NAME, response_format={"type": "json_object"})
        return json.loads(chat.choices[0].message.content)
    except: return None

def generate_poster_prompt(job_title, qualification):
    prompt = f"""Write a text-to-image prompt for a poster: "{job_title}". Qual: {qualification}. Style: Gold/Black, Professional. Output ONLY prompt."""
    try:
        chat = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model=MODEL_NAME)
        return chat.choices[0].message.content
    except: return "Error generating prompt."
    
