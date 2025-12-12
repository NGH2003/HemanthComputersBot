import os
from supabase import create_client, Client

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(url, key)

def get_whatsapp_number():
    try:
        res = supabase.table("settings").select("value").eq("key", "whatsapp_number").execute()
        if res.data: return res.data[0]['value']
        return "919900000000"
    except: return "919900000000"

def add_user(user_id, first_name, username, qual, age, caste, gender):
    data = {
        "user_id": user_id, "first_name": first_name, "username": username,
        "qualification": qual, "age": age, "caste": caste, "gender": gender
    }
    supabase.table("users").upsert(data).execute()

# --- NEW: UPDATE PROFILE ---
def update_user_profile(user_id, field, value):
    """Updates a single field (like age or qual) for a user"""
    supabase.table("users").update({field: value}).eq("user_id", user_id).execute()

def add_job(title, summary, link, min_age, max_age, qual, category, documents):
    data = {
        "title": title, "summary": summary, "apply_link": link,
        "min_age": min_age, "max_age": max_age, "qualification_req": qual,
        "category": category, "documents_req": documents, "is_active": True
    }
    supabase.table("jobs").insert(data).execute()

def update_job(job_id, title, summary, link, min_age, max_age, qual, category, documents):
    data = {
        "title": title, "summary": summary, "apply_link": link,
        "min_age": min_age, "max_age": max_age, "qualification_req": qual,
        "category": category, "documents_req": documents
    }
    supabase.table("jobs").update(data).eq("id", job_id).execute()
    
