import os
from supabase import create_client, Client

# Load keys from Environment Variables (Render)
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(url, key)

def get_whatsapp_number():
    """Fetches admin WhatsApp number from DB, defaults if missing"""
    try:
        res = supabase.table("settings").select("value").eq("key", "whatsapp_number").execute()
        if res.data: return res.data[0]['value']
        return "918970913832" # Change this to your fallback number
    except: return "918970913832"

def add_user(user_id, first_name, username, qual, age, caste, gender):
    """Saves or Updates a User Profile"""
    data = {
        "user_id": user_id, "first_name": first_name, "username": username,
        "qualification": qual, "age": age, "caste": caste, "gender": gender
    }
    supabase.table("users").upsert(data).execute()

def add_job(title, summary, link, min_age, max_age, qual, category, documents):
    """Adds a new Job/Exam/Scholarship"""
    data = {
        "title": title, "summary": summary, "apply_link": link,
        "min_age": min_age, "max_age": max_age, "qualification_req": qual,
        "category": category, "documents_req": documents, "is_active": True
    }
    supabase.table("jobs").insert(data).execute()
