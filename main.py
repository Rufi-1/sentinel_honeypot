from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
import time
import os
import random
import re
import sqlite3
import requests
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

# --- 1. DATABASE SETUP ---
DB_NAME = "honeypot.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS sessions 
                        (id TEXT PRIMARY KEY, persona TEXT, last_reply TEXT, start_time TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS messages 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         session_id TEXT, role TEXT, message TEXT, timestamp TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS evidence 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         session_id TEXT, type TEXT, value TEXT, timestamp TEXT)''')
init_db()

# --- 2. PERSONAS (With BACKUP Replies) ---
CHARACTERS = {
    "grandma": {
        "opener": "Hello? Is this my grandson? I can't read this text very well.",
        "responses": {
            "money": ["I don't use apps... I have cash in a biscuit tin.", "Can I just give the money to the postman?", "I don't know how to transfer."],
            "threat": ["Police?! Oh my god, please don't hurt me!", "I am shaking... let me call my son.", "Please don't block me, I need my phone!"],
            "data": ["Is the code the one on the back of the card?", "Wait, let me find my reading glasses.", "It says 7... 2... wait, I lost my place."],
            "fallback": ["I am getting very confused. Call my landline.", "Hello? Are you still there?", "My hearing aid is whistling."]
        }
    },
    "student": {
        "opener": "Yo, who is this? Do I know you?",
        "responses": {
            "money": ["Bro I have like ₹50. You want that?", "My dad pays the bills, ask him.", "I'm broke until next week."],
            "threat": ["Lol police? Get lost.", "Scare tactics don't work on me.", "Go ahead, block it. I have 3 other accounts."],
            "data": ["You want my OTP? Send a request on the official app.", "Nice try scammer.", "I'm not sharing that over text."],
            "fallback": ["Bro you're making no sense.", "Is this a prank?", "Text me later."]
        }
    },
    "uncle": {
        "opener": "Who gave you this number? Speak fast.",
        "responses": {
            "money": ["I do not transfer money to strangers.", "Send an official invoice first.", "I will visit the branch personally."],
            "threat": ["Do not threaten me! I know the Commissioner.", "I am recording this call for the police.", "You are making a big mistake."],
            "data": ["NEVER ask for OTP. I am blocking you.", "I am reporting this number.", "I will not share confidential info."],
            "fallback": ["State your business clearly.", "Stop wasting my time.", "I am hanging up."]
        }
    }
}

# --- 3. LOGIC CORE ---
def send_guvi_callback(sid):
    try:
        evidence_map = {
            "bankAccounts": [], "upiIds": [], "phishingLinks": [], 
            "phoneNumbers": [], "suspiciousKeywords": []
        }
        
        with sqlite3.connect(DB_NAME) as conn:
            rows = conn.execute("SELECT type, value FROM evidence WHERE session_id=?", (sid,)).fetchall()
            for type_, val in rows:
                if type_ == "Bank Account": evidence_map["bankAccounts"].append(val)
                elif type_ == "UPI ID": evidence_map["upiIds"].append(val)
                elif type_ == "Phone Number": evidence_map["phoneNumbers"].append(val)
                elif type_ == "Link": evidence_map["phishingLinks"].append(val)
                else: evidence_map["suspiciousKeywords"].append(val)
            
            msg_count = conn.execute("SELECT COUNT(*) FROM messages WHERE session_id=?", (sid,)).fetchone()[0]

        payload = {
            "sessionId": sid,
            "scamDetected": True,
            "totalMessagesExchanged": msg_count,
            "extractedIntelligence": evidence_map,
            "agentNotes": f"Scam detected. Captured {len(rows)} data points."
        }
        requests.post("https://hackathon.guvi.in/api/updateHoneyPotFinalResult", json=payload, timeout=2)
    except: pass

def extract_evidence(sid, text):
    """
    PRECISION EXTRACTION: Separates Phones, Banks, and UPIs accurately.
    """
    extracted = []
    
    # 1. UPI IDs (Must contain @)
    upis = re.findall(r'[a-zA-Z0-9\.\-_]+@[a-zA-Z]+', text)
    for u in upis: extracted.append(("UPI ID", u))

    # 2. Phone Numbers (10 digits, starts with 6-9)
    # We use a strict lookahead to ensure it's not part of a longer number
    phones = re.findall(r'(?<!\d)[6-9]\d{9}(?!\d)', text)
    for p in phones: extracted.append(("Phone Number", p))

    # 3. Bank Accounts (9 to 18 digits)
    # We exclude anything that matched as a phone number
    potential_accounts = re.findall(r'\d{9,18}', text)
    for acc in potential_accounts:
        if acc not in phones: # Only add if it's NOT a phone number
            extracted.append(("Bank Account", acc))

    # 4. Keywords (Tactics)
    keywords = ["urgent", "blocked", "sbi", "hdfc", "otp", "police", "jail", "loan", "kyc", "verify"]
    text_lower = text.lower()
    for k in keywords:
        if k in text_lower: extracted.append(("Suspicious Keyword", k.upper()))

    # Save to DB
    if extracted:
        with sqlite3.connect(DB_NAME) as conn:
            for type_, value in extracted:
                exists = conn.execute("SELECT 1 FROM evidence WHERE session_id=? AND value=?", (sid, value)).fetchone()
                if not exists:
                    conn.execute("INSERT INTO evidence (session_id, type, value, timestamp) VALUES (?, ?, ?, ?)",
                                 (sid, type_, value, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()

def get_reply(sid, text, persona_name):
    """
    Selects a reply but prevents repeating the EXACT same phrase twice in a row.
    """
    char = CHARACTERS.get(persona_name, CHARACTERS["grandma"])
    text_lower = text.lower()
    
    # Identify Category
    category = "fallback"
    if any(w in text_lower for w in ["police", "jail", "block", "urgent", "risk"]): category = "threat"
    elif any(w in text_lower for w in ["money", "pay", "cash", "bank", "invoice"]): category = "money"
    elif any(w in text_lower for w in ["otp", "code", "pin", "card", "verify"]): category = "data"
    
    # Get List of Options
    options = char['responses'][category]
    
    # Check Last Reply to avoid repetition
    with sqlite3.connect(DB_NAME) as conn:
        row = conn.execute("SELECT last_reply FROM sessions WHERE id=?", (sid,)).fetchone()
        last_reply = row[0] if row else ""

    # Filter out the last used reply if possible
    valid_options = [opt for opt in options if opt != last_reply]
    
    # If we exhausted options, fall back to the full list
    if not valid_options: valid_options = options
    
    # Pick one
    selected_reply = random.choice(valid_options)
    
    # Update Last Reply in DB
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("UPDATE sessions SET last_reply=? WHERE id=?", (selected_reply, sid))
        conn.commit()
        
    return selected_reply

# --- 4. ENDPOINTS ---
@app.api_route("/{path_name:path}", methods=["GET", "POST"])
async def catch_all(request: Request, path_name: str, bg_tasks: BackgroundTasks):
    # Dashboard & History Endpoints
    if "dashboard" in path_name:
        with sqlite3.connect(DB_NAME) as conn:
            return {"status": "success", "stats": {
                "messages": conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
                "evidence": conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
            }}
            
    if "evidence" in path_name:
        with sqlite3.connect(DB_NAME) as conn:
            data = [{"type": r[0], "value": r[1], "session": r[2]} for r in conn.execute("SELECT type, value, session_id FROM evidence ORDER BY id DESC LIMIT 50")]
            return {"status": "success", "evidence": data}

    if request.method == "GET": return {"status": "ONLINE", "mode": "SMART_FILTER_V2"}

    # Chat Logic
    try:
        try:
            body = await request.body()
            payload = json.loads(body.decode()) if body else {}
        except: payload = {}

        sid = payload.get("sessionId") or "test-session"
        msg = payload.get("message", {})
        user_text = msg.get("text", "") if isinstance(msg, dict) else str(msg)

        # 1. Manage Session
        with sqlite3.connect(DB_NAME) as conn:
            row = conn.execute("SELECT persona FROM sessions WHERE id=?", (sid,)).fetchone()
            if row:
                persona = row[0]
            else:
                persona = random.choice(list(CHARACTERS.keys()))
                conn.execute("INSERT INTO sessions (id, persona, start_time) VALUES (?, ?, ?)", 
                             (sid, persona, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()

        # 2. Reply (With Loop Breaker)
        reply = get_reply(sid, user_text, persona)

        # 3. Tasks
        try:
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO messages (session_id, role, message, timestamp) VALUES (?, ?, ?, ?)",
                            (sid, "scammer", user_text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.execute("INSERT INTO messages (session_id, role, message, timestamp) VALUES (?, ?, ?, ?)",
                            (sid, "agent", reply, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
        except: pass
        
        bg_tasks.add_task(extract_evidence, sid, user_text)
        bg_tasks.add_task(send_guvi_callback, sid)

        return {"status": "success", "reply": reply}

    except Exception as e:
        logger.error(f"Error: {e}")
        return {"status": "error", "reply": "System Error"}
