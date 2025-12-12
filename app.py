import streamlit as st
import threading
import asyncio
import pandas as pd
import time
from db import add_job, update_job, supabase, update_user_coins
from ai_engine import analyze_notification, extract_text_from_pdf, generate_daily_quiz_content, generate_poster_prompt, fetch_rss_feeds, fetch_url_text
from bot_logic import run_bot

# --- CONFIG ---
st.set_page_config(page_title="HC Citizen Admin", layout="wide", page_icon="🏛️")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    [data-testid="stSidebar"] { background-color: #0e1117; }
    [data-testid="stSidebar"] * { color: #ffffff !important; }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] { margin-bottom: 15px !important; }
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

def safe_fetch_jobs(query="", category="All"):
    try:
        req = supabase.table("jobs").select("*").eq("is_active", True)
        if query: req = req.ilike("title", f"%{query}%")
        if category != "All": req = req.eq("category", category)
        return req.execute().data
    except: return []

# --- SIDEBAR ---
with st.sidebar:
    st.title("🏛️ HC Admin")
    menu = st.radio("Navigate", ["📊 Dashboard", "📝 Post & Sync", "🗂️ Manage All", "👥 Users & Tracker", "🎨 Tools (Poster)", "🧠 Quiz Manager", "🤖 Menu Config"])
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
    c1.metric("Users", u); c2.metric("Active Posts", j); c3.metric("Pending Apps", a, delta_color="inverse")

# --- 2. POST & SYNC ---
elif menu == "📝 Post & Sync":
    t1, t2 = st.tabs(["✍️ Manual Post", "🌐 Auto-Sync (Web)"])
    
    with t1:
        st.subheader("Manual Post")
        c1, c2 = st.columns([1, 1])
        with c1:
            cat = st.selectbox("Category", ["GOVT_JOB", "PVT_JOB", "SCHEME", "EXAM", "RESULT", "KEY_ANSWER", "SCHOLARSHIP", "NEWS"])
            up = st.file_uploader("Upload PDF", type=['pdf'])
            if up and st.button("✨ Auto-Fill"):
                with st.spinner("AI Analysis..."):
                    txt = extract_text_from_pdf(up)
                    if txt: st.session_state['new_job'] = analyze_notification(txt, mode=cat); st.success("Filled!")
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
        st.subheader("Fetch from Internet")
        # RSS FEED MANAGEMENT
        with st.expander("⚙️ Manage RSS Feeds"):
            rss_feeds = supabase.table("rss_sources").select("*").execute().data
            for r in rss_feeds:
                c1, c2 = st.columns([4, 1])
                c1.write(f"{r['name']} ({r['url']})")
                if c2.button("🗑️", key=f"del_rss_{r['id']}"):
                    supabase.table("rss_sources").delete().eq("id", r['id']).execute(); st.rerun()
            
            with st.form("add_rss"):
                nm = st.text_input("Source Name")
                ul = st.text_input("RSS URL")
                if st.form_submit_button("Add Source"):
                    supabase.table("rss_sources").insert({"name": nm, "url": ul}).execute(); st.success("Added!"); st.rerun()
        
        # FETCH ACTION (FIXED CRASH HERE)
        if st.button("🔄 Scan All Feeds"):
            # Get URLs from DB
            urls = [r['url'] for r in rss_feeds] if rss_feeds else []
            if not urls:
                st.warning("No RSS feeds found. Add one above!")
            else:
                st.session_state['feeds'] = fetch_rss_feeds(urls)
        
        if 'feeds' in st.session_state:
            for i in st.session_state['feeds']:
                with st.expander(i['title']):
                    st.write(i['summary'])
                    import_cat = st.selectbox("Import As:", ["GOVT_JOB", "SCHEME", "EXAM", "RESULT", "NEWS"], key=f"cat_{i['link']}")
                    if st.button("⬇️ Import", key=i['link']):
                        web = fetch_url_text(i['link'])
                        if len(web)<100: web = i['title']
                        st.session_state['new_job'] = analyze_notification(web, mode=import_cat)
                        st.session_state['new_job']['category'] = import_cat
                        st.success("Imported!"); 

# --- 3. MANAGE ALL ---
elif menu == "🗂️ Manage All":
    st.header("Library")
    c1, c2 = st.columns([3, 1])
    search = c1.text_input("Search")
    cat_filter = c2.selectbox("Category", ["All", "GOVT_JOB", "PVT_JOB", "SCHEME", "EXAM", "RESULT"])
    jobs = safe_fetch_jobs(search, cat_filter)
    for j in jobs:
        with st.expander(f"{j['title']} ({j['category']})"):
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
                if st.button("Delete", key=f"d_{j['id']}"):
                    supabase.table("jobs").update({"is_active": False}).eq("id", j['id']).execute(); st.rerun()

# --- 4. USERS & TRACKER (NEW COIN MANAGER) ---
elif menu == "👥 Users & Tracker":
    t1, t2 = st.tabs(["📊 Tracker", "💰 User Coins"])
    
    with t1:
        st.header("Application Tracker")
        with st.form("new_app"):
            c1, c2 = st.columns(2)
            uid = c1.text_input("User ID"); jt = c2.text_input("Service Name")
            if st.form_submit_button("Add"):
                if uid.isdigit() and jt:
                    supabase.table("user_applications").insert({"user_id": uid, "job_title": jt, "status": "Received"}).execute(); st.success("Added"); st.rerun()
                else: st.error("Invalid Input")
        apps = supabase.table("user_applications").select("*").order("updated_at", desc=True).limit(50).execute().data
        for a in apps:
            c1, c2, c3 = st.columns([2, 3, 2])
            c1.write(f"`{a['user_id']}`")
            c2.write(f"**{a['job_title']}**")
            ns = c3.selectbox("Status", ["Received", "Processing", "Hall Ticket Sent", "Done"], index=["Received", "Processing", "Hall Ticket Sent", "Done"].index(a['status']), key=f"s_{a['id']}", label_visibility="collapsed")
            if ns != a['status']:
                supabase.table("user_applications").update({"status": ns}).eq("id", a['id']).execute(); st.rerun()

    with t2:
        st.header("Manage User Coins")
        u_search = st.text_input("Search User ID or Name")
        
        req = supabase.table("users").select("*").order("coins", desc=True).limit(20)
        if u_search: req = req.or_(f"first_name.ilike.%{u_search}%,user_id.eq.{u_search if u_search.isdigit() else 0}")
        users = req.execute().data
        
        for u in users:
            c1, c2, c3 = st.columns([3, 1, 2])
            c1.write(f"**{u['first_name']}** (`{u['user_id']}`)")
            c2.metric("Coins", u.get('coins', 0))
            
            # Coin Update Form
            with c3.popover("Edit Coins"):
                amount = st.number_input(f"Add/Remove for {u['first_name']}", value=0, key=f"coin_{u['user_id']}")
                if st.button("Update", key=f"upd_{u['user_id']}"):
                    new_bal = update_user_coins(u['user_id'], amount)
                    st.success(f"New Balance: {new_bal}")
                    st.rerun()
            st.divider()

# --- 5. TOOLS ---
elif menu == "🎨 Tools (Poster)":
    st.header("AI Poster")
    jobs = safe_fetch_jobs()
    if jobs:
        jt = st.selectbox("Post", [j['title'] for j in jobs])
        if st.button("Generate Prompt"):
            j = next(x for x in jobs if x['title'] == jt)
            # Ensure generate_poster_prompt is imported and working
            prompt = generate_poster_prompt(j['title'], j['qualification_req'])
            st.code(prompt)

# --- 6. QUIZ ---
elif menu == "🧠 Quiz Manager":
    st.header("Quiz")
    t1, t2, t3 = st.tabs(["Auto", "Manual", "Polls"])
    with t1:
        top = st.selectbox("Topic", ["GK", "History"])
        if st.button("Auto-Gen"):
            q = generate_daily_quiz_content(top)
            if q: supabase.table("quizzes").insert({"question": q['question'], "options": q['options'], "correct_id": 0, "is_sent": False}).execute(); st.success("Queued!")
    with t2:
        with st.form("mq"):
            q = st.text_input("Question")
            o1 = st.text_input("Option 1 (Correct)")
            o2 = st.text_input("Option 2")
            o3 = st.text_input("Option 3")
            o4 = st.text_input("Option 4")
            if st.form_submit_button("Queue"):
                supabase.table("quizzes").insert({"question": q, "options": [o1,o2,o3,o4], "correct_id": 0, "is_sent": False}).execute(); st.success("Queued!")
    with t3:
        with st.form("poll"):
            q = st.text_input("Poll Question")
            o1 = st.text_input("Option 1")
            o2 = st.text_input("Option 2")
            if st.form_submit_button("Broadcast Poll"):
                 supabase.table("quizzes").insert({"question": q, "options": [o1,o2], "correct_id": 0, "is_sent": False}).execute(); st.success("Poll Queued!")

# --- 7. MENU ---
elif menu == "🤖 Menu Config":
    st.header("Menu")
    with st.expander("➕ Add"):
        with st.form("nb"):
            l = st.text_input("Label"); r = st.number_input("Row", 1, 5)
            t = st.selectbox("Type", ["callback", "url"]); d = st.text_input("Data")
            if st.form_submit_button("Add"):
                supabase.table("bot_menus").insert({"label": l, "action_type": t, "action_data": d, "row_order": r}).execute(); st.success("Added!"); st.rerun()
    st.divider()
    btns = supabase.table("bot_menus").select("*").order("row_order").execute().data
    for b in btns:
        c1, c2, c3, c4 = st.columns([0.5, 2, 2, 1])
        c1.write(f"R{b['row_order']}")
        c2.button(b['label'], key=f"p_{b['id']}", disabled=True)
        c3.code(b['action_data'])
        if c4.button("🗑️", key=f"del_{b['id']}"):
            supabase.table("bot_menus").delete().eq("id", b['id']).execute(); st.rerun()
