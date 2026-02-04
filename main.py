from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
import time
import os
import random
import re
import sqlite3
import requests # Added for the callback
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
                        (id TEXT PRIMARY KEY, persona TEXT, start_time TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS messages 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         session_id TEXT, role TEXT, message TEXT, timestamp TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS evidence 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         session_id TEXT, type TEXT, value TEXT, timestamp TEXT)''')
init_db()

# --- 2. PERSONAS ---
CHARACTERS = {
    "grandma": {
        "opener": "Hello? Is this my grandson? I can't read this text very well.",
        "responses": {
            "money": "I don't use apps... I have cash in a biscuit tin. Do you want that?",
            "threat": "Police?! Oh my god, please don't hurt me! I am an old lady.",
            "data": "Is the code the one on the back of the card? It says 7... 2... wait.",
            "fallback": "I am getting very confused. Can you just call my landline?"
        }
    },
    "student": {
        "opener": "Yo, who is this? Do I know you? I'm in a lecture.",
        "responses": {
            "money": "Bro I have like ₹50 in my account. You want that?",
            "threat": "Lol police? For what? Downloading movies? Get lost.",
            "data": "You want my OTP? Send me a request on the official app first.",
            "fallback": "Bro you're making no sense. Is this a prank?"
        }
    },
    "uncle": {
        "opener": "Who gave you this number? Speak fast, I am entering a meeting.",
        "responses": {
            "money": "I do not transfer money to strangers. Send an official invoice.",
            "threat": "Do not threaten me! I know the Commissioner personally.",
            "data": "NEVER ask for OTP. I am blocking this number immediately.",
            "fallback": "State your business clearly or I am hanging up."
        }
    },
    "techie": {
        "opener": "Received. Identify yourself and your encryption protocol.",
        "responses": {
            "money": "I only transact via crypto. Send your wallet address.",
            "threat": "Your IP has been logged. Trace route initiated.",
            "data": "Phishing attempt detected. Nice try script-kiddie.",
            "fallback": "Your social engineering attempt is failing. Try harder."
        }
    },
    "mom": {
        "opener": "Hello? Is this about my son's school fees?",
        "responses": {
            "money": "We are struggling this month. Can I pay half now?",
            "threat": "Please don't block! My son needs this phone for classes!",
            "data": "Okay, okay, I am looking for the card. Please wait...",
            "fallback": "I am very worried. Is everything okay with the account?"
        }
    }
}

# --- 3. INTELLIGENCE & CALLBACK ENGINE ---
def send_guvi_callback(sid):
    """
    Sends the mandatory intelligence report to GUVI.
    Runs in the background so it never slows down the chat.
    """
    try:
        # 1. Gather Intelligence from DB
        evidence_map = {
            "bankAccounts": [], "upiIds": [], "phishingLinks": [], 
            "phoneNumbers": [], "suspiciousKeywords": []
        }
        
        with sqlite3.connect(DB_NAME) as conn:
            # Get evidence
            rows = conn.execute("SELECT type, value FROM evidence WHERE session_id=?", (sid,)).fetchall()
            for type_, val in rows:
                if "Account" in type_: evidence_map["bankAccounts"].append(val)
                elif "UPI" in type_ or "Email" in type_: evidence_map["upiIds"].append(val)
                elif "Phone" in type_: evidence_map["phoneNumbers"].append(val)
                elif "Tactic" in type_ or "Threat" in type_: evidence_map["suspiciousKeywords"].append(val)
                else: evidence_map["suspiciousKeywords"].append(val) # Default bucket
            
            # Get msg count
            msg_count = conn.execute("SELECT COUNT(*) FROM messages WHERE session_id=?", (sid,)).fetchone()[0]

        # 2. Construct Payload
        payload = {
            "sessionId": sid,
            "scamDetected": True, # We always assume it's a scam in this honeypot
            "totalMessagesExchanged": msg_count,
            "extractedIntelligence": evidence_map,
            "agentNotes": f"Scam detected. Captured {len(rows)} data points. Persona used."
        }

        # 3. Send (Fire & Forget)
        # We wrap in try/except because we don't want to crash if their server is down
        requests.post("https://hackathon.guvi.in/api/updateHoneyPotFinalResult", json=payload, timeout=2)
        logger.info(f"🚀 CALLBACK SENT for {sid}")

    except Exception as e:
        logger.error(f"Callback Error: {e}")

def save_message(sid, role, msg):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("INSERT INTO messages (session_id, role, message, timestamp) VALUES (?, ?, ?, ?)",
                         (sid, role, msg, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
    except: pass

def extract_evidence(sid, text):
    extracted = []
    text_lower = text.lower()
    
    # Greedy Regex Extraction
    numbers = re.findall(r'\d+', text)
    for n in numbers:
        if len(n) >= 10: label = "Phone/Account"
        elif len(n) >= 4: label = "OTP/PIN/ID"
        else: label = "Numeric Detail"
        extracted.append((label, n))

    # Keyword Extraction
    keywords = ["urgent", "blocked", "sbi", "hdfc", "otp", "police", "jail", "loan", "kyc"]
    for k in keywords:
        if k in text_lower: extracted.append(("Keyword/Tactic", k.upper()))

    if extracted:
        with sqlite3.connect(DB_NAME) as conn:
            for type_, value in extracted:
                # Avoid exact duplicates
                exists = conn.execute("SELECT 1 FROM evidence WHERE session_id=? AND value=?", (sid, value)).fetchone()
                if not exists:
                    conn.execute("INSERT INTO evidence (session_id, type, value, timestamp) VALUES (?, ?, ?, ?)",
                                 (sid, type_, value, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()

def get_reply(text, persona_name):
    char = CHARACTERS[persona_name]
    text_lower = text.lower()
    if any(w in text_lower for w in ["police", "jail", "block", "urgent"]): return char['responses']['threat']
    if any(w in text_lower for w in ["money", "pay", "cash", "bank"]): return char['responses']['money']
    if any(w in text_lower for w in ["otp", "code", "pin", "card"]): return char['responses']['data']
    return char['responses']['fallback']

# --- 4. ENDPOINTS ---
@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def catch_all(request: Request, path_name: str, bg_tasks: BackgroundTasks):
    
    # --- VISUALIZATION ENDPOINTS ---
    if "evidence" in path_name:
        with sqlite3.connect(DB_NAME) as conn:
            data = [{"type": r[0], "value": r[1], "session": r[2]} for r in conn.execute("SELECT type, value, session_id FROM evidence ORDER BY id DESC LIMIT 50")]
            return {"status": "success", "count": len(data), "evidence": data}

    if "history" in path_name:
        with sqlite3.connect(DB_NAME) as conn:
            parts = path_name.split("/")
            sid = parts[-1] if len(parts) > 0 and parts[-1] != "history" else None
            if sid:
                msgs = [{"role": r[0], "msg": r[1]} for r in conn.execute("SELECT role, message FROM messages WHERE session_id=? ORDER BY id ASC", (sid,))]
                return {"status": "success", "session": sid, "chat": msgs}
            else:
                msgs = [{"session": r[0], "role": r[1], "msg": r[2]} for r in conn.execute("SELECT session_id, role, message FROM messages ORDER BY id DESC LIMIT 50")]
                return {"status": "success", "feed": msgs}

    if "dashboard" in path_name:
        with sqlite3.connect(DB_NAME) as conn:
            return {"status": "success", "stats": {
                "messages": conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
                "evidence": conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
            }}

    if request.method == "GET": return {"status": "ONLINE", "mode": "PROD_CALLBACK_ENABLED"}

    # --- CHAT LOGIC ---
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
            persona = row[0] if row else random.choice(list(CHARACTERS.keys()))
            if not row: conn.execute("INSERT INTO sessions (id, persona, start_time) VALUES (?, ?, ?)", (sid, persona, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        # 2. Reply
        reply = get_reply(user_text, persona)

        # 3. Tasks (Save, Extract, REPORT)
        save_message(sid, "scammer", user_text)
        save_message(sid, "agent", reply)
        bg_tasks.add_task(extract_evidence, sid, user_text)
        
        # *** THE MANDATORY CALLBACK ***
        # We send this on EVERY turn to ensure we capture data even if the scammer stops talking.
        bg_tasks.add_task(send_guvi_callback, sid)

        return {"status": "success", "reply": reply}

    except Exception as e:
        logger.error(f"Error: {e}")
        return {"status": "error", "reply": "System Error"}

