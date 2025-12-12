import os
from datetime import date, timedelta
from supabase import create_client, Client

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# --- USER & COINS ---
def get_whatsapp_number():
    try:
        res = supabase.table("settings").select("value").eq("key", "whatsapp_number").execute()
        return res.data[0]['value'] if res.data else "919900000000"
    except: return "919900000000"

def add_user(user_id, first_name, username, qual, age, caste, gender):
    today = str(date.today())
    res = supabase.table("users").select("coins, last_daily_login").eq("user_id", user_id).execute()
    
    coins = 0
    if res.data:
        u = res.data[0]
        coins = u.get('coins', 0)
        # Daily Login Reward (+1 Coin)
        if u.get('last_daily_login') != today:
            coins += 1
            supabase.table("users").update({"coins": coins, "last_daily_login": today}).eq("user_id", user_id).execute()
    else:
        # New User Bonus (+5 Coins)
        coins = 5 
        data = {
            "user_id": user_id, "first_name": first_name, "username": username,
            "qualification": qual, "age": age, "caste": caste, "gender": gender,
            "coins": coins, "last_daily_login": today
        }
        supabase.table("users").upsert(data).execute()
    return coins

def update_user_coins(user_id, amount):
    """Manually add/remove coins. amount can be negative."""
    res = supabase.table("users").select("coins").eq("user_id", user_id).execute()
    if res.data:
        current = res.data[0]['coins']
        new_bal = max(0, current + int(amount))
        supabase.table("users").update({"coins": new_bal}).eq("user_id", user_id).execute()
        return new_bal
    return 0

def update_user_profile(user_id, field, value):
    supabase.table("users").update({field: value}).eq("user_id", user_id).execute()

def delete_user_profile(user_id):
    supabase.table("users").delete().eq("user_id", user_id).execute()

# --- JOBS & REMINDERS ---
def add_job(title, summary, link, min_age, max_age, qual, category, documents):
    data = {"title": title, "summary": summary, "apply_link": link, "min_age": min_age, "max_age": max_age, "qualification_req": qual, "category": category, "documents_req": documents, "is_active": True}
    supabase.table("jobs").insert(data).execute()

def update_job(job_id, title, summary, link, min_age, max_age, qual, category, documents):
    data = {"title": title, "summary": summary, "apply_link": link, "min_age": min_age, "max_age": max_age, "qualification_req": qual, "category": category, "documents_req": documents}
    supabase.table("jobs").update(data).eq("id", job_id).execute()

def set_reminder(user_id, job_id, last_date_str):
    try:
        y, m, d = map(int, last_date_str.split('-'))
        deadline = date(y, m, d)
        remind_on = deadline - timedelta(days=2)
        supabase.table("job_reminders").insert({"user_id": user_id, "job_id": job_id, "reminder_date": str(remind_on)}).execute()
        return True
    except: return False

# --- DOCS ---
def get_user_docs(user_id):
    return supabase.table("user_docs").select("*").eq("user_id", user_id).execute().data

def add_user_doc(user_id, doc_name, expiry, file_id):
    supabase.table("user_docs").insert({
        "user_id": user_id, "doc_name": doc_name, "expiry_date": expiry, 
        "file_id": file_id, "status": "Valid"
    }).execute()
