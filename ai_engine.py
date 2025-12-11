import os
import json
import pdfplumber
from groq import Groq

# Initialize Groq Client
# Ensure GROQ_API_KEY is set in Render Environment Variables
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# --- CONFIGURATION ---
# We use the new stable model from Groq
MODEL_NAME = "llama-3.3-70b-versatile"

def extract_text_from_pdf(pdf_file):
    """
    Reads text from an uploaded PDF file object.
    Reads only the first 2 pages to save AI tokens and processing time.
    """
    try:
        with pdfplumber.open(pdf_file) as pdf:
            text = ""
            # Limit to first 2 pages (usually contains key dates/eligibility)
            for page in pdf.pages[:2]: 
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        return text
    except Exception as e:
        print(f"PDF Error: {e}")
        return ""

def analyze_notification(raw_text):
    """
    Uses Groq to analyze job text and extract structured JSON data.
    """
    
    # 1. Safety Check for API Key
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {"error": "CRITICAL: GROQ_API_KEY is missing in Render Settings."}

    # 2. System Prompt
    # We instruct the AI to be a data extraction machine.
    prompt = f"""
    You are a Data Extraction Assistant. Analyze this job notification text and return valid JSON ONLY.
    
    RULES:
    1. Extract 'documents' (e.g., Aadhaar, Marks Card, Caste Cert). If not found, output "Standard Documents (Photo, Sign, Aadhaar, Marks Cards)".
    2. Write a 'summary' in a mix of Kannada and English (Kanglish) suitable for Karnataka students.
    3. CRITICAL: Do NOT put the official application URL in the summary. We want users to ask the Admin for the link.
    4. If specific fields (Age/Qualification) are missing, use sensible defaults or "Refer PDF".
    
    JSON Structure to Return:
    {{
        "title": "Job Title",
        "summary": "Short summary in Kannada/English...",
        "min_age": 18, 
        "max_age": 35,
        "qualification": "e.g. Degree / SSLC / PUC",
        "last_date": "DD/MM/YYYY",
        "apply_link": "Official Website URL",
        "documents": "List of required documents..."
    }}

    Raw Text to Analyze: 
    {raw_text[:6000]} 
    """
    
    try:
        # 3. API Call
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=MODEL_NAME, 
            response_format={"type": "json_object"} # Forces valid JSON output
        )
        return json.loads(chat.choices[0].message.content)
    
    except Exception as e:
        # Return the specific error so you see it in the Admin Panel
        return {"error": f"Groq API Failed: {str(e)}"}

def generate_daily_quiz_content(topic):
    """
    Generates a single multiple-choice question for the Daily Quiz feature.
    """
    prompt = f"""
    Generate 1 GK multiple-choice question suitable for Karnataka competitive exams (KPSC, Police, SDA).
    Topic: {topic}
    
    Return JSON ONLY: 
    {{ 
        "question": "Question text?", 
        "options": ["Option A", "Option B", "Option C", "Option D"], 
        "correct_option": "Option A" 
    }}
    """
    try:
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=MODEL_NAME,
            response_format={"type": "json_object"}
        )
        return json.loads(chat.choices[0].message.content)
    except Exception as e:
        print(f"Quiz Error: {e}")
        return None

def generate_poster_prompt(job_title, qualification):
    """
    Generates a detailed text prompt for an Image Generator (like Bing/Ideogram)
    to create a professional poster.
    """
    prompt = f"""
    Act as a professional graphic designer. 
    Write a highly detailed text-to-image prompt to create a promotional notification poster for a Cyber Cafe.
    
    Job Title: "{job_title}"
    Qualification: "{qualification}"
    
    Requirements:
    - Visual Style: Modern, Professional, Gold and Black premium theme.
    - Elements: Computer, documents, Karnataka map outline (subtle).
    - Text Instruction: Ensure the text "Apply at HC" is mentioned in the prompt.
    
    Output ONLY the prompt text. Do not add conversational filler.
    """
    try:
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=MODEL_NAME,
        )
        return chat.choices[0].message.content
    except Exception as e:
        return f"Error generating prompt: {e}"
