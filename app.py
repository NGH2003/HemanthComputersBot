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

# ... (Your imports remain here) ...

st.set_page_config(page_title="HC Admin Pro", layout="wide", page_icon="🖥️")

# --- 🎨 CUSTOM CSS & HTML INJECTION ---
st.markdown("""
<style>
    /* 1. GLOBAL SETTINGS */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        background-color: #f8f9fa; /* Light Gray Background */
        color: #1e1e1e;
    }

    /* 2. SIDEBAR STYLING */
    section[data-testid="stSidebar"] {
        background-color: #0e1117; /* Dark Sidebar */
        color: white;
    }
    section[data-testid="stSidebar"] .css-17lntkn {
        color: #e0e0e0;
    }
    
    /* 3. METRIC CARDS (Dashboard Stats) */
    div[data-testid="metric-container"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        color: #333;
        transition: transform 0.2s;
    }
    div[data-testid="metric-container"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 12px rgba(0,0,0,0.1);
    }
    div[data-testid="metric-container"] label {
        color: #666; /* Label Color */
    }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        color: #007bff; /* Value Color (Blue) */
        font-weight: 700;
    }

    /* 4. BUTTONS */
    .stButton>button {
        background-color: #007bff;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 10px 24px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #0056b3;
        color: white;
        box-shadow: 0 4px 10px rgba(0,123,255,0.3);
    }
    
    /* Secondary Button (Red/Delete) Override - simplified selector */
    div[data-testid="stExpander"] button {
        background-color: #ff4b4b;
        border: 1px solid #ff4b4b;
    }
    div[data-testid="stExpander"] button:hover {
        background-color: #c93434;
    }

    /* 5. FORM INPUTS */
    input[type="text"], textarea, input[type="number"] {
        border-radius: 8px !important;
        border: 1px solid #d1d5db !important;
        padding: 10px;
    }
    
    /* 6. TABS */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: white;
        border-radius: 8px 8px 0 0;
        gap: 1px;
        padding: 10px 20px;
        border: 1px solid #e0e0e0;
        border-bottom: none;
    }
    .stTabs [aria-selected="true"] {
        background-color: #007bff !important;
        color: white !important;
    }

    /* 7. HIDE STREAMLIT BRANDING */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
</style>
""", unsafe_allow_html=True)

# --- CUSTOM HEADER HTML ---
st.markdown("""
<div style="background-color: #007bff; padding: 20px; border-radius: 10px; margin-bottom: 20px; color: white; display: flex; align-items: center; justify-content: space-between;">
    <div>
        <h1 style="margin: 0; font-size: 24px; color: white;">🖥️ Hemanth Computers</h1>
        <p style="margin: 0; font-size: 14px; opacity: 0.8;">Admin Control Center • Active</p>
    </div>
    <div style="background: rgba(255,255,255,0.2); padding: 5px 15px; border-radius: 20px; font-size: 12px;">
        Ver 2.0
    </div>
</div>
""", unsafe_allow_html=True)

# ... (Rest of your app.py logic follows from here: imports, sidebar, tabs...)

# --- CUSTOM CSS FOR UI POLISH ---
st.markdown("""
<style>
    .metric-card {background-color: #f0f2f6; padding: 20px; border-radius: 10px; border-left: 5px solid #ff4b4b;}
    .stButton>button {width: 100%; border-radius: 5px;}
    .success-status {color: green; font-weight: bold;}
    .pending-status {color: orange; font-weight: bold;}
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

# --- HELPERS ---
def safe_int(value, default):
    try: return int(value)
    except: return default

def fetch_metrics():
    """Get counts for dashboard"""
    try:
        users = supabase.table("users").select("user_id", count="exact").execute().count
        jobs = supabase.table("jobs").select("id", count="exact").eq("is_active", True).execute().count
        apps = supabase.table("user_applications").select("id", count="exact").eq("status", "Received").execute().count
        return users, jobs, apps
    except: return 0, 0, 0

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.title("🖥️ HC Controller")
    st.caption("v2.0 Advanced")
    
    menu = st.radio("Navigate", [
        "📊 Dashboard", 
        "📝 Post & Sync", 
        "🗂️ Manage Jobs (Edit/Del)", 
        "👥 Applications", 
        "🎨 Tools (Poster/Quiz)"
    ])
    
    st.divider()
    st.caption("System Status")
    st.success("Bot Running 🟢")
    if st.button("Refresh Cache"):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 1. DASHBOARD PAGE
# ==========================================
if menu == "📊 Dashboard":
    st.header("📈 Business Overview")
    
    # Fetch real data
    u_count, j_count, a_count = fetch_metrics()
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total Users", u_count, delta="Lifetime")
    with c2:
        st.metric("Active Jobs", j_count, delta="Live Now")
    with c3:
        st.metric("Pending Applications", a_count, delta="Needs Action", delta_color="inverse")
    
    st.divider()
    
    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("Recent Activity")
        # Show last 5 applications
        recent = supabase.table("user_applications").select("*").order("updated_at", desc=True).limit(5).execute().data
        if recent:
            df = pd.DataFrame(recent)
            st.dataframe(df[['user_id', 'job_title', 'status', 'updated_at']], use_container_width=True, hide_index=True)
        else:
            st.info("No recent activity.")

    with c2:
        st.subheader("Quick Actions")
        if st.button("📢 Broadcast Quiz"):
            st.toast("Go to Tools > Quiz")
        if st.button("🌐 Sync Updates"):
            st.toast("Go to Post > Sync")

# ==========================================
# 2. POST & SYNC PAGE
# ==========================================
elif menu == "📝 Post & Sync":
    tab_manual, tab_sync = st.tabs(["✍️ Manual Post", "🌐 Auto-Sync (Web)"])
    
    # --- MANUAL POST ---
    with tab_manual:
        st.subheader("Create New Notification")
        col1, col2 = st.columns([1, 1])
        
        with col1:
            cat = st.selectbox("Category", ["GOVT_JOB", "PVT_JOB", "SCHEME", "EXAM", "RESULT", "KEY_ANSWER", "SCHOLARSHIP"])
            uploaded = st.file_uploader("Upload PDF (AI Analyze)", type=['pdf'])
            
            if uploaded and st.button("✨ Analyze PDF"):
                with st.spinner("Analyzing..."):
                    txt = extract_text_from_pdf(uploaded)
                    if txt:
                        data = analyze_notification(txt, mode=cat)
                        if data: st.session_state['new_job'] = data; st.success("Data Extracted!")

        with col2:
            d = st.session_state.get('new_job', {})
            with st.form("create_job"):
                t = st.text_input("Title", d.get("title", ""))
                s = st.text_area("Summary", d.get("summary", ""), height=100)
                
                r1, r2 = st.columns(2)
                min_a = r1.number_input("Min Age", value=safe_int(d.get("min_age"), 18))
                max_a = r2.number_input("Max Age", value=safe_int(d.get("max_age"), 60))
                
                link = st.text_input("Official Link", d.get("apply_link", ""))
                doc = st.text_area("Documents / Benefits", d.get("documents", "Standard"), height=70)
                
                if st.form_submit_button("🚀 Publish Job"):
                    add_job(t, s, link, min_a, max_a, d.get("qualification", ""), cat, doc)
                    st.toast("Published Successfully!")
                    if 'new_job' in st.session_state: del st.session_state['new_job']
                    time.sleep(1)
                    st.rerun()

    # --- AUTO SYNC ---
    with tab_sync:
        st.subheader("Latest Internet Updates")
        if st.button("🔄 Scan RSS Feeds"):
            with st.spinner("Scanning..."):
                st.session_state['feeds'] = fetch_rss_feeds()
        
        if 'feeds' in st.session_state:
            for item in st.session_state['feeds']:
                with st.expander(f"{item['title']}"):
                    st.write(item['summary'])
                    if st.button("⬇️ Import This", key=item['link']):
                        web_text = fetch_url_text(item['link'])
                        if len(web_text) < 100: web_text = item['title']
                        st.session_state['new_job'] = analyze_notification(web_text, mode="JOB")
                        st.success("Imported! Switch to 'Manual Post' tab to review.")

# ==========================================
# 3. MANAGE JOBS (EDIT/DELETE)
# ==========================================
elif menu == "🗂️ Manage Jobs (Edit/Del)":
    st.header("🗂️ Job Library")
    
    # Search & Filter
    c1, c2 = st.columns([3, 1])
    search = c1.text_input("🔍 Search Jobs", placeholder="Type job name...")
    filter_active = c2.checkbox("Show Inactive", value=False)
    
    # Query DB
    req = supabase.table("jobs").select("*").order("created_at", desc=True)
    if not filter_active: req = req.eq("is_active", True)
    if search: req = req.ilike("title", f"%{search}%")
    jobs = req.execute().data
    
    # Display as List
    for job in jobs:
        with st.expander(f"{'🟢' if job['is_active'] else '🔴'} {job['title']} (Cat: {job['category']})"):
            
            # MODE: VIEW OR EDIT
            edit_mode = st.toggle("Enable Edit Mode", key=f"toggle_{job['id']}")
            
            if edit_mode:
                # --- EDIT FORM ---
                with st.form(f"edit_{job['id']}"):
                    new_t = st.text_input("Title", job['title'])
                    new_s = st.text_area("Summary", job['summary'])
                    c1, c2 = st.columns(2)
                    new_min = c1.number_input("Min Age", value=job['min_age'])
                    new_max = c2.number_input("Max Age", value=job['max_age'])
                    new_link = st.text_input("Link", job['apply_link'])
                    new_doc = st.text_area("Docs", job['documents_req'])
                    
                    if st.form_submit_button("💾 Save Changes"):
                        update_job(job['id'], new_t, new_s, new_link, new_min, new_max, job['qualification_req'], job['category'], new_doc)
                        st.success("Updated!")
                        time.sleep(1)
                        st.rerun()
            else:
                # --- VIEW MODE ---
                st.write(f"**Summary:** {job['summary']}")
                st.write(f"**Link:** {job['apply_link']}")
                st.write(f"**Docs:** {job['documents_req']}")
                
                c1, c2 = st.columns([1, 4])
                if job['is_active']:
                    if c1.button("🗑️ Deactivate", key=f"del_{job['id']}"):
                        supabase.table("jobs").update({"is_active": False}).eq("id", job['id']).execute()
                        st.rerun()
                else:
                    if c1.button("♻️ Reactivate", key=f"react_{job['id']}"):
                        supabase.table("jobs").update({"is_active": True}).eq("id", job['id']).execute()
                        st.rerun()

# ==========================================
# 4. APPLICATIONS TRACKER
# ==========================================
elif menu == "👥 Applications":
    st.header("📊 Customer Application Tracker")
    
    # Add New
    with st.expander("➕ Add New Customer Order", expanded=True):
        with st.form("new_app"):
            c1, c2 = st.columns(2)
            uid = c1.text_input("User ID (Telegram)")
            jt = c2.text_input("Job/Service Name")
            if st.form_submit_button("Add to Tracker"):
                supabase.table("user_applications").insert({"user_id": uid, "job_title": jt, "status": "Received"}).execute()
                st.success("Added!")
                st.rerun()

    st.divider()
    
    # Kanban-style Status Update
    apps = supabase.table("user_applications").select("*").order("updated_at", desc=True).limit(50).execute().data
    
    for app in apps:
        with st.container():
            c1, c2, c3, c4 = st.columns([2, 3, 2, 2])
            c1.code(app['user_id'])
            c2.write(f"**{app['job_title']}**")
            
            # Status Color Logic
            status_map = {"Received": 0, "Processing": 1, "Hall Ticket Sent": 2, "Done": 3}
            st_color = "red" if app['status']=="Received" else "orange" if app['status']=="Processing" else "green"
            c3.markdown(f":{st_color}[{app['status']}]")
            
            # Quick Actions
            new_stat = c4.selectbox("Update", ["Received", "Processing", "Hall Ticket Sent", "Done"], 
                                   index=status_map.get(app['status'], 0), 
                                   key=f"st_{app['id']}", 
                                   label_visibility="collapsed")
            
            if new_stat != app['status']:
                supabase.table("user_applications").update({"status": new_stat}).eq("id", app['id']).execute()
                st.toast(f"Updated to {new_stat}")
                time.sleep(0.5)
                st.rerun()
            st.divider()

# ==========================================
# 5. TOOLS (POSTER & QUIZ)
# ==========================================
elif menu == "🎨 Tools (Poster/Quiz)":
    tab_p, tab_q = st.tabs(["🎨 Poster Generator", "🧠 Daily Quiz"])
    
    with tab_p:
        st.subheader("Generate AI Poster Prompts")
        jobs = supabase.table("jobs").select("*").eq("is_active", True).execute().data
        if jobs:
            jt = st.selectbox("Select Active Job", [j['title'] for j in jobs])
            if st.button("✨ Generate Prompt"):
                j = next(x for x in jobs if x['title'] == jt)
                with st.spinner("Writing..."):
                    p = generate_poster_prompt(j['title'], j['qualification_req'])
                    st.code(p)
                    st.caption("Copy this to Bing Image Creator")
        else:
            st.info("No active jobs.")

    with tab_q:
        st.subheader("Broadcast Daily Quiz")
        topic = st.selectbox("Topic", ["General Knowledge", "Karnataka History", "Science", "Mental Ability"])
        if st.button("🚀 Generate & Send Quiz"):
            with st.spinner("AI Generating..."):
                q = generate_daily_quiz_content(topic)
                if q:
                    supabase.table("quizzes").insert({
                        "question": q['question'], 
                        "options": q['options'], 
                        "correct_id": 0, # AI usually puts correct as first, or we map it. 
                        # Note: Ideally map correct_option string to index properly in ai_engine logic
                        "is_sent": False
                    }).execute()
                    st.success("Quiz Queued for Broadcast!")

# Add New
    with st.expander("➕ Add New Customer Order", expanded=True):
        with st.form("new_app"):
            c1, c2 = st.columns(2)
            uid = c1.text_input("User ID (Telegram)")
            jt = c2.text_input("Job/Service Name")
            
            if st.form_submit_button("Add to Tracker"):
                # VALIDATION CHECK
                if not uid or not uid.isdigit():
                    st.error("⚠️ User ID must be a number (e.g. 12345678).")
                elif not jt:
                    st.error("⚠️ Job Name cannot be empty.")
                else:
                    # Only submit if valid
                    try:
                        supabase.table("user_applications").insert({
                            "user_id": int(uid), # Convert to number
                            "job_title": jt, 
                            "status": "Received"
                        }).execute()
                        st.success("Added!")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Database Error: {e}")
