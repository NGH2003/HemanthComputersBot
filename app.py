import streamlit as st
import threading
import asyncio
import os
from db import add_job, supabase
from ai_engine import analyze_notification, extract_text_from_pdf, generate_daily_quiz_content, generate_poster_prompt
from bot_logic import run_bot

st.set_page_config(page_title="HC Admin", layout="wide")

# --- BOT BACKGROUND RUNNER ---
def start_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_bot())

if 'bot_started' not in st.session_state:
    threading.Thread(target=start_bot, daemon=True).start()
    st.session_state['bot_started'] = True

# --- UI HEADER ---
st.title("🖥️ HC Job & Exam Controller")
st.caption(f"Bot Status: {'Running' if st.session_state.get('bot_started') else 'Stopped'}")

# Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📝 Post Job", "🎨 Poster Gen", "🗂️ Job Library", "📊 Status Tracker", "🧠 Daily Quiz"])

# --- TAB 1: POST JOB (FIXED) ---
with tab1:
    st.header("1. Upload Notification")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        cat = st.selectbox("Category", ["GOVT_JOB", "PVT_JOB", "EXAM", "SCHOLARSHIP"])
        uploaded = st.file_uploader("Upload PDF Notification", type=['pdf'])
        
        if uploaded and st.button("✨ Analyze PDF"):
            with st.spinner("AI is reading the file..."):
                # 1. Extract Text
                txt = extract_text_from_pdf(uploaded)
                
                # Debug: Check if PDF was read
                if not txt or len(txt) < 50:
                    st.error("⚠️ Could not read text from PDF. It might be an image/scan. Please fill details manually.")
                else:
                    # 2. Analyze with Groq
                    data = analyze_notification(txt)
                    if data: 
                        st.session_state['job_data'] = data
                        st.success("Analysis Complete!")
                    else:
                        st.error("⚠️ AI Error: Check your GROQ_API_KEY in Render Settings.")

    # --- THE FORM (Now Outside the logic, so it always shows) ---
    with col2:
        st.subheader("2. Review & Post")
        
        # Load defaults from AI if available, else empty
        d = st.session_state.get('job_data', {})
        
        with st.form("job_entry_form"):
            t = st.text_input("Job Title", value=d.get("title", ""))
            s = st.text_area("Kannada Summary", value=d.get("summary", ""), height=100)
            
            c1, c2 = st.columns(2)
            with c1:
                min_a = st.number_input("Min Age", value=int(d.get("min_age", 18)))
                qual = st.text_input("Qualification", value=d.get("qualification", ""))
            with c2:
                max_a = st.number_input("Max Age", value=int(d.get("max_age", 35)))
                link = st.text_input("Official Link (Hidden)", value=d.get("apply_link", ""))
                
            doc = st.text_area("Required Documents", value=d.get("documents", "Standard Documents"), height=70)
            
            if st.form_submit_button("✅ Post to Bot"):
                add_job(t, s, link, min_a, max_a, qual, cat, doc)
                st.success(f"Successfully Posted: {t}")
                # Clear session to prevent duplicate posts
                if 'job_data' in st.session_state:
                    del st.session_state['job_data']

# --- TAB 2: POSTER GENERATOR ---
with tab2:
    st.header("🎨 Poster Prompt Generator")
    jobs = supabase.table("jobs").select("*").eq("is_active", True).execute().data
    
    if not jobs:
        st.info("No active jobs found. Post a job in Tab 1 first.")
    else:
        jt = st.selectbox("Select Job", [j['title'] for j in jobs])
        
        if st.button("Generate Prompt"):
            j = next(x for x in jobs if x['title'] == jt)
            with st.spinner("Writing prompt..."):
                prompt_text = generate_poster_prompt(j['title'], j['qualification_req'])
                st.code(prompt_text)
                st.caption("Copy above text to Bing Image Creator or Ideogram.")

# --- TAB 3: JOB LIBRARY ---
with tab3:
    st.subheader("Manage Active Jobs")
    q = st.text_input("Search")
    res = supabase.table("jobs").select("*").eq("is_active", True).ilike("title", f"%{q}%").execute().data
    
    if not res:
        st.write("No active jobs.")
        
    for j in res:
        with st.expander(f"{j['title']} (Ends: {j.get('last_date', 'N/A')})"):
            st.write(f"Link: {j['apply_link']}")
            st.link_button("Go to Official Site ↗️", j['apply_link'])
            if st.button("Delete", key=f"del_{j['id']}"):
                supabase.table("jobs").update({"is_active": False}).eq("id", j['id']).execute()
                st.rerun()

# --- TAB 4: STATUS TRACKER ---
with tab4:
    st.subheader("Customer Applications")
    with st.form("new_app"):
        c1, c2 = st.columns(2)
        with c1: uid = st.text_input("User ID (Telegram ID)")
        with c2: jt = st.text_input("Job Name")
        if st.form_submit_button("Track Application"):
            supabase.table("user_applications").insert({"user_id": uid, "job_title": jt, "status": "Received"}).execute()
            st.success("Added!")
            
    st.divider()
    apps = supabase.table("user_applications").select("*").order("updated_at", desc=True).limit(20).execute().data
    for a in apps:
        c1, c2, c3 = st.columns([1,2,2])
        c1.write(f"User: `{a['user_id']}`")
        c2.write(f"**{a['job_title']}**")
        
        status_options = ["Received", "Processing", "Hall Ticket Sent", "Done"]
        curr_idx = status_options.index(a['status']) if a['status'] in status_options else 0
        
        new_stat = c3.selectbox("Status", status_options, index=curr_idx, key=f"st_{a['id']}")
        if new_stat != a['status']:
            supabase.table("user_applications").update({"status": new_stat}).eq("id", a['id']).execute()
            st.toast("Status Updated!")

# --- TAB 5: DAILY QUIZ ---
with tab5:
    st.subheader("Daily GK Quiz")
    topic = st.selectbox("Topic", ["General Knowledge", "Karnataka History", "Science", "Mental Ability"])
    
    if st.button("Auto-Generate Question"):
        with st.spinner("AI Generating..."):
            q = generate_daily_quiz_content(topic)
            if q:
                supabase.table("quizzes").insert({"question": q['question'], "options": q['options'], "correct_id": ["A","B","C","D"].index(q['correct_option']), "is_sent": False}).execute()
                st.success("Quiz Queued! Check Telegram Channel.")
