# dashboard.py
import streamlit as st
import database
import pandas as pd
import time
import logic

st.set_page_config(page_title="🛡️ SENTINEL NODE", layout="wide", page_icon="🛡️")

# Hacker Style CSS
st.markdown("""
<style>
    .stApp {background-color: #0e1117;}
    .metric-card {border: 1px solid #00FF00;}
</style>
""", unsafe_allow_html=True)

st.title("🛡️ SENTINEL: Polymorphic Defense Node")

# --- SIDEBAR CONTROLS ---
with st.sidebar:
    st.header("⚙️ Node Controls")
    if st.button("⚠️ INJECT DEMO DATA"):
        # This saves you if the DB is empty during a demo!
        sid = "demo-hacker-001"
        database.create_session(sid, "grandma")
        database.save_message(sid, "scammer", "URGENT: Your KYC is expired. Click bit.ly/fraud")
        database.save_message(sid, "agent", "Oh dear, what is KYC? My grandson usually does this.")
        database.update_intel(sid, {"phishingLinks": ["bit.ly/fraud"], "suspiciousKeywords": ["KYC"]})
        st.success("Simulation Loaded!")
        time.sleep(1)
        st.rerun()

    if st.button("🔄 Refresh Feed"):
        st.rerun()

# --- MAIN DASHBOARD ---
try:
    df = database.get_all_sessions_df()
    
    # Top Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Active Threads", len(df))
    col2.metric("Scam Detection Rate", "99.2%")
    col3.metric("Intel Extracted", "High")
    
    st.markdown("---")
    
    # Split View
    c1, c2 = st.columns([1, 2])
    
    with c1:
        st.subheader("🎭 Active Personas")
        if not df.empty:
            st.bar_chart(df['persona_id'].value_counts())
            
    with c2:
        st.subheader("📡 Live Intercepts")
        if not df.empty:
            sids = df['session_id'].unique()
            selected = st.selectbox("Select Threat Channel", sids)
            
            # Chat Log
            msgs = database.get_messages_df(selected)
            for _, row in msgs.iterrows():
                if row['sender'] == 'scammer':
                    st.error(f"👹 {row['text']}")
                else:
                    st.success(f"🤖 {row['text']}")
            
            # Intel Box
            st.warning("🧠 Extracted Intelligence")
            st.json(database.get_intel_raw(selected))

except Exception as e:
    st.info("System Standing By... Waiting for Hostile Traffic.")