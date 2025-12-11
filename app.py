import streamlit as st
import threading
import asyncio
import pandas as pd
import time
from datetime import datetime
from db import add_job, update_job, supabase
from ai_engine import analyze_notification, extract_text_from_pdf, generate_daily_quiz_content, generate_poster_prompt, fetch_rss_feeds, fetch_url_text
from bot_logic import run_bot

# --- CONFIG ---
st.set_page_config(page_title="HC Admin Pro", layout="wide", page_icon="🖥️")

# --- 🎨 FIXED UI & CSS ---
st.markdown("""
<style>
    /* 1. GLOBAL FONTS & THEME */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* 2. SIDEBAR FIX (Text Visibility) */
    [data-testid="stSidebar"] {
        background-color: #0e1117;
    }
    /* Force all text in sidebar to be White */
    [data-testid="stSidebar"] * {
        color: #ffffff !important;
    }
    /* Fix Radio Button Selection Color in Sidebar */
    [data-testid="stSidebar"] div[role="radiogroup"] label {
        color: #ffffff !important;
    }

    /* 3. MAIN CONTENT CARDS */
    div[data-testid="metric-container"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    
    /* 4. BUTTON STYLING */
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
    }
    
    /* 5. FORM INPUTS */
    input, textarea, select {
        border-radius: 8px !important;
    }

    /* 6. HIDE DEFAULT ELEMENTS */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
</style>
""", unsafe_allow_html=True)

# --- BOT THREAD MANAGER ---
def start_bot_thread():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_bot())
    except Exception as e: print(e)

if "HC_Bot_Thread" not in [t.name for t in threading.enumerate()]:
    threading.Thread(target=start_bot_thread, name="HC_Bot_Thread", daemon=True).start()

# --- HELPERS (With Crash Fix) ---
def safe_int(value, default):
    """Prevents app crash if AI returns 'Refer PDF' instead of a number"""
    try:
        # Remove any non-digit characters just in case
        clean_val = ''.join(filter(str.isdigit, str(value)))
        return int(clean_val)
    except:
        return default

def fetch_metrics():
    try:
        users = supabase.table("users").select("user_id", count="exact").execute().count
        jobs = supabase.table("jobs").select("id", count="exact").eq("is_active", True).execute().count
        apps = supabase.table("user_applications").select("id", count="exact").eq("status", "Received").execute().count
        return users, jobs, apps
    except: return 0, 0, 0

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.title("🖥️ HC Controller")
    st.caption("v2.1 UI Fixed")
    
    menu = st.radio("Navigate", [
        "📊 Dashboard", 
        "📝 Post & Sync", 
        "🗂️ Manage Jobs", 
        "👥 Applications", 
        "🎨 Tools"
    ])
    
    st.divider()
    st.caption("System Status")
    st.success("Bot Running 🟢")
    if st.button("Refresh Cache"):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 1. DASHBOARD
# ==========================================
if menu == "📊 Dashboard":
    st.header("📈 Business Overview")
    u_count, j_count, a_count = fetch_metrics()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Users", u_count)
    c2.metric("Active Jobs", j_count)
    c3.metric("Pending Apps", a_count, delta_color="inverse")
    
    st.divider()
    st.subheader("Recent Activity")
    recent = supabase.table("user_applications").select("*").order("updated_at", desc=True).limit(5).execute().data
    if recent:
        st.dataframe(pd.DataFrame(recent)[['user_id', 'job_title', 'status']], use_container_width=True, hide_index=True)

# ==========================================
# 2. POST & SYNC
# ==========================================
elif menu == "📝 Post & Sync":
    tab_m, tab_s = st.tabs(["✍️ Manual Post", "🌐 Auto-Sync"])
    
    with tab_m:
        st.subheader("Create Notification")
        c1, c2 = st.columns([1, 1])
        with c1:
            cat = st.selectbox("Category", ["GOVT_JOB", "PVT_JOB", "SCHEME", "EXAM", "RESULT", "KEY_ANSWER", "SCHOLARSHIP"])
            up = st.file_uploader("Upload PDF", type=['pdf'])
            if up and st.button("✨ Analyze PDF"):
                with st.spinner("Analyzing..."):
                    txt = extract_text_from_pdf(up)
                    if txt:
                        data = analyze_notification(txt, mode=cat)
                        if data: st.session_state['new_job'] = data; st.success("Done!")

        with c2:
            d = st.session_state.get('new_job', {})
            with st.form("job_form"):
                t = st.text_input("Title", d.get("title", ""))
                s = st.text_area("Summary", d.get("summary", ""), height=100)
                r1, r2 = st.columns(2)
                # CRASH FIX: Using safe_int
                min_a = r1.number_input("Min Age", value=safe_int(d.get("min_age"), 18))
                max_a = r2.number_input("Max Age", value=safe_int(d.get("max_age"), 60))
                link = st.text_input("Link", d.get("apply_link", ""))
                doc = st.text_area("Docs", d.get("documents", "Standard"), height=70)
                
                if st.form_submit_button("🚀 Publish"):
                    add_job(t, s, link, min_a, max_a, d.get("qualification", ""), cat, doc)
                    st.success("Published!")
                    if 'new_job' in st.session_state: del st.session_state['new_job']
                    time.sleep(1); st.rerun()

    with tab_s:
        if st.button("🔄 Scan Internet"):
            with st.spinner("Scanning..."): st.session_state['feeds'] = fetch_rss_feeds()
        if 'feeds' in st.session_state:
            for i in st.session_state['feeds']:
                with st.expander(i['title']):
                    st.write(i['summary'])
                    if st.button("⬇️ Import", key=i['link']):
                        web_txt = fetch_url_text(i['link'])
                        if len(web_txt)<100: web_txt = i['title']
                        st.session_state['new_job'] = analyze_notification(web_txt, mode="JOB")
                        st.success("Imported! Go to Manual Post tab.")

# ==========================================
# 3. MANAGE JOBS
# ==========================================
elif menu == "🗂️ Manage Jobs":
    st.header("Job Library")
    search = st.text_input("🔍 Search", placeholder="Job name...")
    req = supabase.table("jobs").select("*").order("created_at", desc=True)
    if search: req = req.ilike("title", f"%{search}%")
    jobs = req.execute().data
    
    for j in jobs:
        with st.expander(f"{'🟢' if j['is_active'] else '🔴'} {j['title']}"):
            edit = st.toggle("Edit", key=f"e_{j['id']}")
            if edit:
                with st.form(f"f_{j['id']}"):
                    nt = st.text_input("Title", j['title'])
                    ns = st.text_area("Summary", j['summary'])
                    if st.form_submit_button("Save"):
                        update_job(j['id'], nt, ns, j['apply_link'], j['min_age'], j['max_age'], j['qualification_req'], j['category'], j['documents_req'])
                        st.success("Saved!"); st.rerun()
            else:
                st.write(j['summary'])
                if j['is_active']:
                    if st.button("Delete (Deactivate)", key=f"d_{j['id']}"):
                        supabase.table("jobs").update({"is_active": False}).eq("id", j['id']).execute(); st.rerun()

# ==========================================
# 4. APPLICATIONS
# ==========================================
elif menu == "👥 Applications":
    st.header("Tracker")
    with st.form("add_app"):
        c1, c2 = st.columns(2)
        uid = c1.text_input("User ID")
        jt = c2.text_input("Job Name")
        if st.form_submit_button("Add"):
            if uid.isdigit() and jt:
                supabase.table("user_applications").insert({"user_id": uid, "job_title": jt, "status": "Received"}).execute()
                st.success("Added"); st.rerun()
            else: st.error("Invalid ID or Job Name")

    st.divider()
    apps = supabase.table("user_applications").select("*").order("updated_at", desc=True).limit(50).execute().data
    for a in apps:
        c1, c2, c3 = st.columns([2, 3, 2])
        c1.write(f"`{a['user_id']}`")
        c2.write(f"**{a['job_title']}**")
        ns = c3.selectbox("Status", ["Received", "Processing", "Hall Ticket Sent", "Done"], 
                         index=["Received", "Processing", "Hall Ticket Sent", "Done"].index(a['status']), 
                         key=f"s_{a['id']}", label_visibility="collapsed")
        if ns != a['status']:
            supabase.table("user_applications").update({"status": ns}).eq("id", a['id']).execute(); st.rerun()

# ==========================================
# 5. TOOLS
# ==========================================
elif menu == "🎨 Tools":
    t1, t2 = st.tabs(["Poster", "Quiz"])
    with t1:
        jobs = supabase.table("jobs").select("*").eq("is_active", True).execute().data
        if jobs:
            jt = st.selectbox("Job", [j['title'] for j in jobs])
            if st.button("Generate Prompt"):
                j = next(x for x in jobs if x['title'] == jt)
                st.code(generate_poster_prompt(j['title'], j['qualification_req']))
    with t2:
        top = st.selectbox("Topic", ["GK", "History"])
        if st.button("Send Quiz"):
            q = generate_daily_quiz_content(top)
            if q: 
                supabase.table("quizzes").insert({"question": q['question'], "options": q['options'], "correct_id": 0, "is_sent": False}).execute()
                st.success("Queued!")
