import os
import json
import pdfplumber
from groq import Groq

# Initialize Groq Client
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"

def extract_text_from_pdf(pdf_file):
    """Reads text from uploaded PDF (First 2 pages)"""
    try:
        with pdfplumber.open(pdf_file) as pdf:
            text = ""
            for page in pdf.pages[:3]: # Read first 3 pages for better detail
                extracted = page.extract_text()
                if extracted: text += extracted + "\n"
        return text
    except Exception as e:
        return ""

def analyze_notification(raw_text):
    """
    Groq Analysis: Returns JSON with Form Data AND a Detailed Markdown Report.
    """
    
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {"error": "CRITICAL: GROQ_API_KEY is missing."}

    prompt = f"""
    You are an Expert Job Analyst. Analyze this notification and return valid JSON.
    
    PART 1: DATA EXTRACTION (For Database)
    Extract Title, Age, Dates, Link, Documents.
    
    PART 2: DETAILED ANALYTICS (For Human Report)
    Generate a professional "Detailed Analytics" report (in Markdown) exactly like this structure:
    1. Critical Dates & Schedule (Application window, Exam date, Correction window).
    2. Examination Pattern (Shifts, Timings, Duration in a table format).
    3. Application Fees (Category wise fee structure in a table).
    4. Technical Requirements (Photo/Sign dimensions, file size).
    5. Syllabus/Eligibility Structure (Brief bullet points).
    
    Return JSON Structure:
    {{
        "title": "Job Title",
        "summary": "Short Kanglish summary (2 lines)",
        "min_age": 18, 
        "max_age": 35,
        "qualification": "Degree",
        "last_date": "DD/MM/YYYY",
        "apply_link": "URL",
        "documents": "List of docs...",
        "detailed_analysis": "MarkDown String of the detailed report here..."
    }}

    Text: {raw_text[:8000]} 
    """
    
    try:
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=MODEL_NAME, 
            response_format={"type": "json_object"}
        )
        return json.loads(chat.choices[0].message.content)
    except Exception as e:
        return {"error": f"Groq API Failed: {str(e)}"}

# ... (Keep generate_daily_quiz_content and generate_poster_prompt exactly as they were) ...
# (Re-paste them here if you need the full file again, otherwise just update analyze_notification)
def generate_daily_quiz_content(topic):
    prompt = f"""Generate 1 GK multiple-choice question for Karnataka students. Topic: {topic}. Return JSON: {{ "question": "...", "options": ["A", "B", "C", "D"], "correct_option": "A" }}"""
    try:
        chat = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model=MODEL_NAME, response_format={"type": "json_object"})
        return json.loads(chat.choices[0].message.content)
    except: return None

def generate_poster_prompt(job_title, qualification):
    prompt = f"""Act as a designer. Write a text-to-image prompt for a poster: "{job_title}". Qual: {qualification}. Style: Gold/Black, Professional. Output ONLY prompt."""
    try:
        chat = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model=MODEL_NAME)
        return chat.choices[0].message.content
    except: return "Error generating prompt."
