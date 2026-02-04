from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
import time
import os
import random
import re
import sqlite3
from datetime import datetime

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. DATABASE SETUP (The "Vault") ---
DB_NAME = "honeypot.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        # Table 1: Sessions
        conn.execute('''CREATE TABLE IF NOT EXISTS sessions 
                        (id TEXT PRIMARY KEY, persona TEXT, start_time TEXT)''')
        # Table 2: Messages (The Conversation)
        conn.execute('''CREATE TABLE IF NOT EXISTS messages 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         session_id TEXT, role TEXT, message TEXT, timestamp TEXT)''')
        # Table 3: Evidence (Stolen Data)
        conn.execute('''CREATE TABLE IF NOT EXISTS evidence 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         session_id TEXT, type TEXT, value TEXT, timestamp TEXT)''')

init_db()

# --- 2. PERSONAS ---
CHARACTERS = {
    "grandma": {
        "opener": "Hello? Is this my grandson? I can't read this text very well.",
        "style": "confused",
        "responses": {
            "money": "I don't use apps... I have cash in a biscuit tin. Do you want that?",
            "threat": "Police?! Oh my god, please don't hurt me! I am an old lady.",
            "data": "Is the code the one on the back of the card? It says 7... 2... wait.",
            "fallback": "I am getting very confused. Can you just call my landline?"
        }
    },
    "student": {
        "opener": "Yo, who is this? Do I know you? I'm in a lecture.",
        "style": "skeptical",
        "responses": {
            "money": "Bro I have like ₹50 in my account. You want that?",
            "threat": "Lol police? For what? Downloading movies? Get lost.",
            "data": "You want my OTP? Send me a request on the official app first.",
            "fallback": "Bro you're making no sense. Is this a prank?"
        }
    },
    "uncle": {
        "opener": "Who gave you this number? Speak fast, I am entering a meeting.",
        "style": "aggressive",
        "responses": {
            "money": "I do not transfer money to strangers. Send an official invoice.",
            "threat": "Do not threaten me! I know the Commissioner personally.",
            "data": "NEVER ask for OTP. I am blocking this number immediately.",
            "fallback": "State your business clearly or I am hanging up."
        }
    },
    "techie": {
        "opener": "Received. Identify yourself and your encryption protocol.",
        "style": "arrogant",
        "responses": {
            "money": "I only transact via crypto. Send your wallet address.",
            "threat": "Your IP has been logged. Trace route initiated.",
            "data": "Phishing attempt detected. Nice try script-kiddie.",
            "fallback": "Your social engineering attempt is failing. Try harder."
        }
    },
    "mom": {
        "opener": "Hello? Is this about my son's school fees?",
        "style": "anxious",
        "responses": {
            "money": "We are struggling this month. Can I pay half now?",
            "threat": "Please don't block! My son needs this phone for classes!",
            "data": "Okay, okay, I am looking for the card. Please wait...",
            "fallback": "I am very worried. Is everything okay with the account?"
        }
    }
}

# --- 3. LOGIC CORE ---
def save_message(sid, role, msg):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT INTO messages (session_id, role, message, timestamp) VALUES (?, ?, ?, ?)",
                     (sid, role, msg, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

def extract_evidence(sid, text):
    """Extracts Phone, UPI, Bank A/C from scammer text and saves to DB."""
    text_lower = text.lower()
    extracted = []
    
    # Extract Phone Numbers
    phones = re.findall(r'(?:\+91|0)?[6-9]\d{9}', text)
    for p in phones: extracted.append(("Phone", p))
    
    # Extract UPI
    upis = re.findall(r'[\w\.-]+@[\w\.-]+', text)
    for u in upis: extracted.append(("UPI", u))
    
    # Extract Bank Accounts (Simple digit check)
    if "account" in text_lower or "ac" in text_lower:
        accounts = re.findall(r'\b\d{9,18}\b', text)
        for a in accounts: extracted.append(("Bank Account", a))

    # Save to DB
    if extracted:
        with sqlite3.connect(DB_NAME) as conn:
            for type_, value in extracted:
                conn.execute("INSERT INTO evidence (session_id, type, value, timestamp) VALUES (?, ?, ?, ?)",
                             (sid, type_, value, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                logger.info(f"🚨 EVIDENCE CAPTURED: {type_} -> {value}")

def get_reply(text, persona_name):
    char = CHARACTERS[persona_name]
    text_lower = text.lower()
    
    # Pattern Matching
    if any(w in text_lower for w in ["police", "jail", "block", "urgent"]):
        return char['responses']['threat']
    if any(w in text_lower for w in ["money", "pay", "cash", "bank"]):
        return char['responses']['money']
    if any(w in text_lower for w in ["otp", "code", "pin", "card"]):
        return char['responses']['data']
    
    # Regex Reflection
    numbers = re.findall(r'\d+', text)
    if numbers and len(numbers[0]) > 4:
        if persona_name == "grandma": return f"I see the number {numbers[0]}... is that the amount?"
        if persona_name == "techie": return f"Numeric string {numbers[0]} captured."
        
    return char['responses']['fallback']

# --- 4. ENDPOINTS ---
@app.api_route("/{path_name:path}", methods=["GET", "POST"])
async def catch_all(request: Request, path_name: str, bg_tasks: BackgroundTasks):
    
    # --- A. VIEW EVIDENCE (New!) ---
    if "evidence" in path_name:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.execute("SELECT type, value, timestamp, session_id FROM evidence ORDER BY id DESC LIMIT 20")
            data = [{"type": r[0], "value": r[1], "time": r[2], "session": r[3]} for r in cursor.fetchall()]
            return {"status": "success", "captured_evidence": data}

    # --- B. VIEW HISTORY ---
    if "history" in path_name:
        parts = path_name.split("/")
        sid = parts[-1] if len(parts) > 0 else None
        
        with sqlite3.connect(DB_NAME) as conn:
            # If specific ID
            if sid and "history" not in sid:
                cursor = conn.execute("SELECT role, message, timestamp FROM messages WHERE session_id=?", (sid,))
                msgs = [{"role": r[0], "message": r[1], "time": r[2]} for r in cursor.fetchall()]
                return {"status": "success", "session_id": sid, "conversation": msgs}
            # Else show all sessions
            else:
                cursor = conn.execute("SELECT id, persona, start_time FROM sessions ORDER BY rowid DESC LIMIT 10")
                sessions = [{"id": r[0], "persona": r[1], "time": r[2]} for r in cursor.fetchall()]
                return {"status": "success", "recent_sessions": sessions}

    # --- C. DASHBOARD ---
    if "dashboard" in path_name:
        with sqlite3.connect(DB_NAME) as conn:
            # Count stats
            total_msgs = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            total_evidence = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
            return {
                "status": "success", 
                "total_messages_processed": total_msgs,
                "total_evidence_captured": total_evidence,
                "system_status": "ARMED"
            }

    if request.method == "GET":
        return {"status": "ONLINE", "system": "Sentinel Forensic Vault"}

    # --- D. CHAT HANDLER ---
    try:
        try:
            body = await request.body()
            payload = json.loads(body.decode()) if body else {}
        except: payload = {}

        sid = payload.get("sessionId") or "test-session"
        msg = payload.get("message", {})
        user_text = msg.get("text", "") if isinstance(msg, dict) else str(msg)

        # 1. Manage Session in DB
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.execute("SELECT persona FROM sessions WHERE id=?", (sid,))
            row = cursor.fetchone()
            
            if row:
                persona = row[0]
            else:
                persona = random.choice(list(CHARACTERS.keys()))
                conn.execute("INSERT INTO sessions (id, persona, start_time) VALUES (?, ?, ?)", 
                             (sid, persona, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                logger.info(f"⚡ NEW SESSION: {sid} as {persona}")

        # 2. Generate Reply
        reply = get_reply(user_text, persona)

        # 3. Save Conversation to DB
        save_message(sid, "scammer", user_text)
        save_message(sid, "agent", reply)

        # 4. Extract Evidence (Background)
        bg_tasks.add_task(extract_evidence, sid, user_text)

        return {"status": "success", "reply": reply}

    except Exception as e:
        logger.error(f"Error: {e}")
        return {"status": "error", "reply": "System Error"}
