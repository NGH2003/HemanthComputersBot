import os
import json
import pdfplumber
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def extract_text_from_pdf(pdf_file):
    """Reads text from uploaded PDF"""
    try:
        with pdfplumber.open(pdf_file) as pdf:
            text = ""
            for page in pdf.pages[:2]: # Read first 2 pages
                extracted = page.extract_text()
                if extracted: text += extracted + "\n"
        return text
    except: return ""

def analyze_notification(raw_text):
    """Groq Llama 3: Extracts Job Details"""
    prompt = f"""
    Analyze this job text. Return JSON ONLY.
    
    RULES:
    1. Extract 'documents' (e.g., Aadhaar, Marks Card). If not found, use "Standard Docs".
    2. Write a 'summary' in Kannada/English (Mixed).
    3. CRITICAL: Do NOT put the application URL in the summary. Keep it hidden.
    
    Structure:
    {{
        "title": "Job Title",
        "summary": "Short summary here...",
        "min_age": 18, "max_age": 35,
        "qualification": "Degree/SSLC",
        "last_date": "DD/MM/YYYY",
        "apply_link": "URL",
        "documents": "List of docs..."
    }}

    Text: {raw_text[:8000]}
    """
    try:
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-8b-8192",
            response_format={"type": "json_object"}
        )
        return json.loads(chat.choices[0].message.content)
    except: return None

def generate_daily_quiz_content(topic):
    """Groq Llama 3: Generates a GK Question"""
    prompt = f"""
    Generate 1 GK multiple-choice question for Karnataka students. Topic: {topic}.
    Return JSON: {{ "question": "...", "options": ["A", "B", "C", "D"], "correct_option": "A" }}
    """
    try:
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-8b-8192",
            response_format={"type": "json_object"}
        )
        return json.loads(chat.choices[0].message.content)
    except: return None

# --- NEW FUNCTION: GROQ POSTER PROMPT ---
def generate_poster_prompt(job_title, qualification):
    """Uses Groq to write an image prompt"""
    prompt = f"""
    Act as a professional graphic designer. 
    Write a highly detailed text-to-image prompt to create a notification poster for: "{job_title}".
    
    Details to include in prompt:
    - Qualification: {qualification}
    - Style: Professional, Gold and Black theme, Cyber Cafe aesthetic.
    - Text overlay instruction: "Apply at HC".
    
    Output ONLY the prompt text. No conversational filler.
    """
    try:
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-8b-8192",
        )
        return chat.choices[0].message.content
    except: return "Error generating prompt."
