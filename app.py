import streamlit as st
import threading
import asyncio
import os
import google.generativeai as genai
from db import add_job, supabase
from ai_engine import analyze_notification, extract_text_from_pdf, generate_daily_quiz_content
from bot_logic import run_bot

# Config
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
st.set_page_config(page_title="HC Admin", layout="wide")

# Bot Thread (Keeps bot alive alongside website)
def start_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_bot())

if 'bot_started' not in st.session_state:
    threading.Thread(target=start_bot, daemon=True).start()
    st.session_state['bot_started'] = True

# UI Headers
st.title("🖥️ HC Job & Exam Controller")
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📝 Post Job", "🎨 Poster Gen", "🗂️ Job Library", "📊 Status Tracker", "🧠 Daily Quiz"])

# TAB 1: POST JOB (AI Analysis)
with tab1:
    cat = st.selectbox("Category", ["GOVT_JOB", "PVT_JOB", "EXAM", "SCHOLARSHIP"])
    uploaded = st.file_uploader("Upload PDF Notification", type=['pdf'])
    
    if uploaded and st.button("Analyze PDF"):
        with st.spinner("Groq AI analyzing..."):
            txt = extract_text_from_pdf(uploaded)
            data = analyze_notification(txt)
            if data: st.session_state['job_data'] = data

    if 'job_data' in st.session_state:
        d = st.session_state['job_data']
        with st.form("job"):
            t = st.text_input("Title", d.get("title"))
            s = st.text_area("Summary", d.get("summary"))
            doc = st.text_area("Required Docs (AI Detected)", d.get("documents"))
            l = st.text_input("Official Link (Admin Only)", d.get("apply_link"))
            if st.form_submit_button("✅ Post to Bot"):
                add_job(t, s, l, d.get("min_age", 0), d.get("max_age", 0), d.get("qualification", ""), cat, doc)
                st.success("Posted Successfully!")

# TAB 2: POSTER GENERATOR (Gemini)
with tab2:
    jobs = supabase.table("jobs").select("*").eq("is_active", True).execute().data
    jt = st.selectbox("Select Job for Poster", [j['title'] for j in jobs]) if jobs else None
    if st.button("Generate Image Prompt") and jt:
        j = next(x for x in jobs if x['title'] == jt)
        prompt = f"Create a professional gold/black poster for '{j['title']}'. Text: 'Apply at HC'. Qual: {j['qualification_req']}."
        res = genai.GenerativeModel('gemini-1.5-flash').generate_content(prompt)
        st.code(res.text)
        st.caption("Copy above text to Bing Image Creator or Ideogram.")

# TAB 3: JOB LIBRARY (Search & Manage)
with tab3:
    q = st.text_input("Search Active Jobs")
    res = supabase.table("jobs").select("*").eq("is_active", True).ilike("title", f"%{q}%").execute().data
    for j in res:
        with st.expander(f"{j['title']} (Ends: {j.get('last_date', 'N/A')})"):
            st.write(f"Link: {j['apply_link']}")
            st.link_button("Go to Official Site ↗️", j['apply_link'])
            if st.button("Delete", key=j['id']):
                supabase.table("jobs").update({"is_active": False}).eq("id", j['id']).execute()
                st.rerun()

# TAB 4: STATUS TRACKER (Customer Service)
with tab4:
    with st.form("new_app"):
        st.write("Add New Customer Application")
        uid = st.text_input("User ID (Telegram ID)")
        jt = st.text_input("Job Name")
        if st.form_submit_button("Track"):
            supabase.table("user_applications").insert({"user_id": uid, "job_title": jt, "status": "Received"}).execute()
            st.success("Added to Tracker")
            
    st.divider()
    apps = supabase.table("user_applications").select("*").order("updated_at", desc=True).limit(10).execute().data
    for a in apps:
        c1, c2, c3 = st.columns([1,2,1])
        c1.write(f"User: {a['user_id']}")
        c2.write(f"{a['job_title']} ({a['status']})")
        if c3.button("Mark: Hall Ticket Sent", key=f"s_{a['id']}"):
            supabase.table("user_applications").update({"status": "Hall Ticket Sent"}).eq("id", a['id']).execute()
            st.rerun()

# TAB 5: DAILY QUIZ (Groq Auto-Gen)
with tab5:
    topic = st.selectbox("Quiz Topic", ["General Knowledge", "Karnataka History", "Science", "Mental Ability"])
    if st.button("Auto-Generate Question"):
        with st.spinner("AI Generating..."):
            q = generate_daily_quiz_content(topic)
            if q:
                supabase.table("quizzes").insert({"question": q['question'], "options": q['options'], "correct_id": ["A","B","C","D"].index(q['correct_option']), "is_sent": False}).execute()
                st.success("Quiz Queued! Will broadcast in 1 minute.")
