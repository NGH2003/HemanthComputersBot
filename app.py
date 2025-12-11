import streamlit as st
import threading
import asyncio
import os
from db import add_job, supabase
from ai_engine import analyze_notification, extract_text_from_pdf, generate_daily_quiz_content, generate_poster_prompt, fetch_rss_feeds, fetch_url_text
from bot_logic import run_bot

st.set_page_config(page_title="HC Admin", layout="wide")

def start_bot_thread():
    try:
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop); loop.run_until_complete(run_bot())
    except Exception as e: print(e)

if "HC_Bot_Thread" not in [t.name for t in threading.enumerate()]:
    threading.Thread(target=start_bot_thread, name="HC_Bot_Thread", daemon=True).start()

def safe_int(value, default):
    try: return int(value)
    except: return default

st.title("🖥️ HC Job & Exam Controller")
st.caption("Bot Status: 🟢 Running")

# NEW TABS
tab1, tab_sync, tab2, tab3, tab4, tab5 = st.tabs(["📝 Post Manually", "🌐 Sync Center", "🎨 Poster", "🗂️ Library", "📊 Tracker", "🧠 Quiz"])

# --- TAB 1: MANUAL POST ---
with tab1:
    st.header("Upload Notification")
    col1, col2 = st.columns([1, 1])
    with col1:
        cat = st.selectbox("Category", ["GOVT_JOB", "PVT_JOB", "SCHEME", "EXAM", "RESULT", "KEY_ANSWER", "SCHOLARSHIP"])
        uploaded = st.file_uploader("Upload PDF", type=['pdf'])
        if uploaded and st.button("✨ Analyze PDF"):
            with st.spinner("AI Analysis..."):
                txt = extract_text_from_pdf(uploaded)
                if txt:
                    data = analyze_notification(txt, mode=cat) # Pass Category Mode
                    if data: st.session_state['job_data'] = data; st.success("Done!")

    if 'job_data' in st.session_state:
        d = st.session_state['job_data']
        with st.expander("📄 Detailed Report", expanded=True): st.markdown(d.get("detailed_analysis", ""))

    with col2:
        st.subheader("Review & Post")
        d = st.session_state.get('job_data', {})
        with st.form("job"):
            t = st.text_input("Title", d.get("title", ""))
            s = st.text_area("Summary", d.get("summary", ""), height=100)
            c1, c2 = st.columns(2)
            c1.number_input("Min Age", value=safe_int(d.get("min_age"), 18))
            c2.number_input("Max Age", value=safe_int(d.get("max_age"), 60))
            link = st.text_input("Link", d.get("apply_link", ""))
            doc = st.text_area("Docs/Benefits", d.get("documents", "Standard"), height=70)
            if st.form_submit_button("✅ Post"):
                add_job(t, s, link, safe_int(d.get("min_age"), 18), safe_int(d.get("max_age"), 60), d.get("qualification", ""), cat, doc)
                st.success("Posted!")

# --- TAB SYNC: AUTO FETCH (NEW) ---
with tab_sync:
    st.header("🌐 Sync Center (Auto-Fetch)")
    st.caption("Fetches latest updates from OneIndia, FreeJobAlert, etc.")
    
    if st.button("🔄 Fetch Latest Updates"):
        with st.spinner("Scanning Internet..."):
            feeds = fetch_rss_feeds()
            st.session_state['feeds'] = feeds
            st.success(f"Found {len(feeds)} Updates!")

    if 'feeds' in st.session_state:
        for item in st.session_state['feeds']:
            with st.expander(f"{item['title']} ({item['published']})"):
                st.write(item['summary'])
                st.write(f"Source: {item['link']}")
                
                # THE IMPORT BUTTON
                if st.button("⬇️ Import & Analyze", key=item['link']):
                    with st.spinner("Scraping & Analyzing..."):
                        # 1. Scrape Text from Webpage
                        web_text = fetch_url_text(item['link'])
                        if len(web_text) < 100: web_text = item['title'] + " " + item['summary'] # Fallback
                        
                        # 2. Analyze with AI
                        data = analyze_notification(web_text, mode="JOB")
                        st.session_state['job_data'] = data
                        st.success("Imported to 'Post Manually' Tab! Go there to review.")

# --- (Tabs 2, 3, 4, 5 remain standard) ---
with tab2: # Poster
    jobs = supabase.table("jobs").select("*").eq("is_active", True).execute().data
    if jobs:
        jt = st.selectbox("Job", [j['title'] for j in jobs])
        if st.button("Generate Prompt"):
            j = next(x for x in jobs if x['title'] == jt)
            st.code(generate_poster_prompt(j['title'], j['qualification_req']))

with tab3: # Library
    q = st.text_input("Search")
    res = supabase.table("jobs").select("*").eq("is_active", True).ilike("title", f"%{q}%").execute().data
    for j in res:
        with st.expander(j['title']):
            if st.button("Delete", key=j['id']):
                supabase.table("jobs").update({"is_active": False}).eq("id", j['id']).execute(); st.rerun()

with tab4: # Status
    with st.form("new"):
        uid = st.text_input("User ID"); jt = st.text_input("Job")
        if st.form_submit_button("Add"):
            supabase.table("user_applications").insert({"user_id": uid, "job_title": jt, "status": "Received"}).execute(); st.success("Added")
    apps = supabase.table("user_applications").select("*").order("updated_at", desc=True).limit(10).execute().data
    for a in apps:
        c1, c2 = st.columns([3, 1])
        c1.write(f"{a['user_id']} - {a['job_title']} ({a['status']})")
        if c2.button("Done", key=f"s_{a['id']}"):
            supabase.table("user_applications").update({"status": "Done"}).eq("id", a['id']).execute(); st.rerun()

with tab5: # Quiz
    topic = st.selectbox("Topic", ["GK", "History"])
    if st.button("Generate"):
        q = generate_daily_quiz_content(topic)
        if q: supabase.table("quizzes").insert({"question": q['question'], "options": q['options'], "correct_id": 0, "is_sent": False}).execute(); st.success("Queued!")
            
