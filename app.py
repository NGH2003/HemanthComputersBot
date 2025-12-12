import streamlit as st
import threading
import asyncio
import pandas as pd
import time
from db import add_job, update_job, supabase
from ai_engine import analyze_notification, extract_text_from_pdf, generate_daily_quiz_content, generate_poster_prompt, fetch_rss_feeds, fetch_url_text
from bot_logic import run_bot

# --- CONFIG ---
st.set_page_config(page_title="HC Citizen Admin", layout="wide", page_icon="🏛️")

import streamlit as st
# ... other imports ...

# 1. CONFIG
st.set_page_config(page_title="HC Citizen Admin", layout="wide", page_icon="🏛️")

# 2. PASTE YOUR CSS HERE
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    [data-testid="stSidebar"] { background-color: #0e1117; }
    [data-testid="stSidebar"] * { color: #ffffff !important; }
    div[data-testid="metric-container"] { background-color: #ffffff; border: 1px solid #e0e0e0; padding: 15px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
    .stButton>button { border-radius: 8px; font-weight: 600; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# 3. REST OF THE APP
# ... start_bot_thread() ...


# --- CSS INJECTION (Dark Sidebar, Clean UI) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    [data-testid="stSidebar"] { background-color: #0e1117; }
    [data-testid="stSidebar"] * { color: #ffffff !important; }
    div[data-testid="metric-container"] { background-color: #ffffff; border: 1px solid #e0e0e0; padding: 15px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
    .stButton>button { border-radius: 8px; font-weight: 600; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- BOT THREAD ---
def start_bot_thread():
    try:
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop); loop.run_until_complete(run_bot())
    except Exception as e: print(e)

if "HC_Bot_Thread" not in [t.name for t in threading.enumerate()]:
    threading.Thread(target=start_bot_thread, name="HC_Bot_Thread", daemon=True).start()

def safe_int(value, default):
    try: return int(''.join(filter(str.isdigit, str(value))))
    except: return default

def safe_fetch_jobs(query=""):
    try:
        req = supabase.table("jobs").select("*").eq("is_active", True)
        if query: req = req.ilike("title", f"%{query}%")
        return req.execute().data
    except: return []

# --- SIDEBAR ---
with st.sidebar:
    st.title("🏛️ HC Admin")
    menu = st.radio("Navigate", ["📊 Dashboard", "📝 Post & Sync", "🗂️ Manage Jobs", "👥 Applications", "🎨 Tools", "🤖 Menu Config"])
    st.success("Bot Running 🟢")
    if st.button("Refresh"): st.cache_data.clear(); st.rerun()

# --- 1. DASHBOARD ---
if menu == "📊 Dashboard":
    st.header("📈 Overview")
    try:
        u = supabase.table("users").select("user_id", count="exact").execute().count
        j = supabase.table("jobs").select("id", count="exact").eq("is_active", True).execute().count
        a = supabase.table("user_applications").select("id", count="exact").eq("status", "Received").execute().count
    except: u=0; j=0; a=0
    c1, c2, c3 = st.columns(3)
    c1.metric("Users", u); c2.metric("Active Jobs", j); c3.metric("Pending Apps", a, delta_color="inverse")

# --- 2. POST & SYNC ---
elif menu == "📝 Post & Sync":
    t1, t2 = st.tabs(["Manual Post", "Auto-Sync"])
    with t1:
        c1, c2 = st.columns([1, 1])
        with c1:
            cat = st.selectbox("Category", ["GOVT_JOB", "PVT_JOB", "SCHEME", "EXAM", "RESULT", "KEY_ANSWER", "SCHOLARSHIP"])
            up = st.file_uploader("Upload PDF", type=['pdf'])
            if up and st.button("✨ Analyze PDF"):
                with st.spinner("AI Analysis..."):
                    txt = extract_text_from_pdf(up)
                    if txt: st.session_state['new_job'] = analyze_notification(txt, mode=cat); st.success("Done!")
        with c2:
            d = st.session_state.get('new_job', {})
            with st.form("job"):
                t = st.text_input("Title", d.get("title", ""))
                s = st.text_area("Summary", d.get("summary", ""), height=100)
                r1, r2 = st.columns(2)
                min_a = r1.number_input("Min Age", value=safe_int(d.get("min_age"), 18))
                max_a = r2.number_input("Max Age", value=safe_int(d.get("max_age"), 60))
                link = st.text_input("Link", d.get("apply_link", ""))
                doc = st.text_area("Docs", d.get("documents", "Standard"), height=70)
                if st.form_submit_button("🚀 Publish"):
                    add_job(t, s, link, min_a, max_a, d.get("qualification", ""), cat, doc)
                    st.success("Published!"); time.sleep(1); st.rerun()
    with t2:
        if st.button("🔄 Scan Internet"):
            st.session_state['feeds'] = fetch_rss_feeds()
        if 'feeds' in st.session_state:
            for i in st.session_state['feeds']:
                with st.expander(i['title']):
                    st.write(i['summary'])
                    if st.button("⬇️ Import", key=i['link']):
                        web = fetch_url_text(i['link'])
                        if len(web)<100: web = i['title']
                        st.session_state['new_job'] = analyze_notification(web, mode="JOB")
                        st.success("Imported! Go to Manual Post tab.")

# --- 3. MANAGE JOBS ---
elif menu == "🗂️ Manage Jobs":
    st.header("Job Library")
    search = st.text_input("Search")
    jobs = safe_fetch_jobs(search)
    for j in jobs:
        with st.expander(f"{j['title']}"):
            edit = st.toggle("Edit Mode", key=f"e_{j['id']}")
            if edit:
                with st.form(f"f_{j['id']}"):
                    nt = st.text_input("Title", j['title'])
                    ns = st.text_area("Summary", j['summary'])
                    if st.form_submit_button("Save"):
                        update_job(j['id'], nt, ns, j['apply_link'], j['min_age'], j['max_age'], j['qualification_req'], j['category'], j['documents_req'])
                        st.success("Updated!"); st.rerun()
            else:
                st.write(j['summary'])
                if st.button("Delete", key=f"d_{j['id']}"):
                    supabase.table("jobs").update({"is_active": False}).eq("id", j['id']).execute(); st.rerun()

# --- 4. TRACKER ---
elif menu == "👥 Applications":
    st.header("Tracker")
    with st.form("new_app"):
        c1, c2 = st.columns(2)
        uid = c1.text_input("User ID"); jt = c2.text_input("Job Name")
        if st.form_submit_button("Add"):
            if uid.isdigit() and jt:
                supabase.table("user_applications").insert({"user_id": uid, "job_title": jt, "status": "Received"}).execute()
                st.success("Added"); st.rerun()
            else: st.error("Invalid Input")
    st.divider()
    apps = supabase.table("user_applications").select("*").order("updated_at", desc=True).limit(50).execute().data
    for a in apps:
        c1, c2, c3 = st.columns([2, 3, 2])
        c1.write(f"`{a['user_id']}`")
        c2.write(f"**{a['job_title']}**")
        ns = c3.selectbox("Status", ["Received", "Processing", "Hall Ticket Sent", "Done"], index=["Received", "Processing", "Hall Ticket Sent", "Done"].index(a['status']), key=f"s_{a['id']}", label_visibility="collapsed")
        if ns != a['status']:
            supabase.table("user_applications").update({"status": ns}).eq("id", a['id']).execute(); st.rerun()

# --- 5. TOOLS ---
elif menu == "🎨 Tools":
    t1, t2 = st.tabs(["Poster", "Quiz"])
    with t1:
        jobs = safe_fetch_jobs()
        if jobs:
            jt = st.selectbox("Job", [j['title'] for j in jobs])
            if st.button("Generate Prompt"):
                j = next(x for x in jobs if x['title'] == jt)
                st.code(generate_poster_prompt(j['title'], j['qualification_req']))
    with t2:
        top = st.selectbox("Topic", ["GK", "History"])
        if st.button("Send Quiz"):
            q = generate_daily_quiz_content(top)
            if q: supabase.table("quizzes").insert({"question": q['question'], "options": q['options'], "correct_id": 0, "is_sent": False}).execute(); st.success("Queued!")

# --- 6. MENU CONFIG ---
elif menu == "🤖 Menu Config":
    st.header("Bot Menu Manager")
    with st.expander("➕ Add Button"):
        with st.form("nb"):
            l = st.text_input("Label"); r = st.number_input("Row", min_value=1, value=5)
            t = st.selectbox("Type", ["callback", "url"]); d = st.text_input("Data (cat_NAME or URL)")
            if st.form_submit_button("Add"):
                supabase.table("bot_menus").insert({"label": l, "action_type": t, "action_data": d, "row_order": r}).execute()
                st.success("Added!"); st.rerun()
    st.divider()
    btns = supabase.table("bot_menus").select("*").order("row_order").execute().data
    for b in btns:
        c1, c2, c3, c4 = st.columns([0.5, 2, 2, 1])
        c1.write(f"R{b['row_order']}")
        c2.button(b['label'], key=f"p_{b['id']}", disabled=True)
        c3.code(b['action_data'])
        if c4.button("🗑️", key=f"del_{b['id']}"):
            supabase.table("bot_menus").delete().eq("id", b['id']).execute(); st.rerun()
            
