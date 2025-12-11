import os
import json
import requests
import feedparser
import pdfplumber
from bs4 import BeautifulSoup
from groq import Groq

# Initialize Groq
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"

# --- 1. NEW: WEB SCRAPER & RSS FETCHER ---
def fetch_rss_feeds():
    """Pulls latest updates from trusted Indian Job/Scheme sources"""
    feeds = [
        "https://kannada.oneindia.com/rss/feeds/kannada-jobs-fb.xml",
        "https://www.freejobalert.com/feed",
        "https://kannada.news18.com/commonfeeds/v1/kannada/rss/career.xml"
    ]
    
    found_items = []
    for url in feeds:
        try:
            f = feedparser.parse(url)
            for entry in f.entries[:5]: # Get top 5 from each
                found_items.append({
                    "title": entry.title,
                    "link": entry.link,
                    "summary": getattr(entry, 'summary', 'No summary'),
                    "published": getattr(entry, 'published', 'Today')
                })
        except: continue
    return found_items

def fetch_url_text(url):
    """Scrapes text from a website link (for the Sync feature)"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        # Kill javascript and css
        for script in soup(["script", "style"]):
            script.extract()
            
        text = soup.get_text()
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        return text[:10000] # Limit to 10k chars for AI
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

# --- 2. UPDATED AI ANALYSIS (Smart Mode) ---
def analyze_notification(raw_text, mode="JOB"):
    """
    Analyzes text based on mode: JOB, SCHEME, or RESULT.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key: return {"error": "CRITICAL: GROQ_API_KEY is missing."}

    # Dynamic Prompt based on Category
    if mode == "SCHEME":
        focus_prompt = """
        This is a GOVERNMENT SCHEME.
        1. Extract 'Benefits' (e.g. Rs 2000/month, Free Rice). Put this in 'summary'.
        2. Extract 'Beneficiaries' (e.g. Women, Farmers, SC/ST). Put this in 'qualification'.
        3. Extract 'Documents Required'.
        """
    elif mode in ["RESULT", "KEY_ANSWER"]:
        focus_prompt = """
        This is an EXAM RESULT or KEY ANSWER.
        1. Extract the Exam Name.
        2. Extract the Link to check result.
        3. Keep summary very short (e.g., "FDA 2024 Results announced.").
        """
    else: # JOB or EXAM
        focus_prompt = """
        This is a JOB or EXAM notification.
        1. Extract Job Title, Age, Qualification.
        2. Extract Documents needed.
        """

    prompt = f"""
    Analyze this text and return JSON ONLY.
    {focus_prompt}
    
    PART 2: DETAILED ANALYTICS (Markdown Report)
    Generate a professional "Detailed Report" (Markdown) covering:
    - Key Highlights / Benefits
    - Eligibility / Beneficiaries
    - Important Dates
    - Steps to Apply / Check
    
    Structure:
    {{
        "title": "Title", 
        "summary": "Short Kanglish summary (2 lines)", 
        "min_age": 18, "max_age": 60,
        "qualification": "Eligibility (e.g. Degree / Women Head of Family)", 
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

# --- (Keep other generators same) ---
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
    
