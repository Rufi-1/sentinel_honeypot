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
            "money": "I don't use apps... I have cash in a biscuit tin.",
            "threat": "Police?! Oh my god, please don't hurt me!",
            "data": "Is the code the one on the back of the card? It says 7... 2...",
            "fallback": "I am getting very confused. Call my landline."
        }
    },
    "student": {
        "opener": "Yo, who is this? Do I know you?",
        "responses": {
            "money": "Bro I have like ₹50. You want that?",
            "threat": "Lol police? Get lost.",
            "data": "You want my OTP? Send a request on the official app.",
            "fallback": "Bro you're making no sense."
        }
    },
    "uncle": {
        "opener": "Who gave you this number? Speak fast.",
        "responses": {
            "money": "I do not transfer money to strangers.",
            "threat": "Do not threaten me! I know the Commissioner.",
            "data": "NEVER ask for OTP. I am blocking you.",
            "fallback": "State your business clearly."
        }
    }
}

# --- 3. LOGIC CORE ---
def save_message(sid, role, msg):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("INSERT INTO messages (session_id, role, message, timestamp) VALUES (?, ?, ?, ?)",
                         (sid, role, msg, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
    except Exception as e:
        logger.error(f"DB Error: {e}")

def extract_evidence(sid, text):
    """
    HYPER-GREEDY MODE: Captures Keywords, Small Numbers, and Scammer Tactics.
    This guarantees evidence is captured even if no phone number is present.
    """
    text_lower = text.lower()
    extracted = []
    
    # 1. Capture Target Entities (Banks, Brands)
    keywords = {
        "sbi": "Target Bank", "hdfc": "Target Bank", "icici": "Target Bank",
        "paytm": "Target App", "gpay": "Target App", "phonepe": "Target App",
        "loan": "Scam Context", "kyc": "Scam Context", "lottery": "Scam Context"
    }
    for word, label in keywords.items():
        if word in text_lower:
            extracted.append((label, word.upper()))

    # 2. Capture Threat Indicators
    threats = {
        "blocked": "Threat Tactic", "suspended": "Threat Tactic", 
        "police": "Coercion", "jail": "Coercion", "urgent": "Urgency Tactic"
    }
    for word, label in threats.items():
        if word in text_lower:
            extracted.append((label, word.upper()))

    # 3. Capture Requested Data (What they want)
    requests = {
        "otp": "Data Requested", "pin": "Data Requested", 
        "cvv": "Data Requested", "password": "Data Requested", 
        "account number": "Data Requested"
    }
    for word, label in requests.items():
        if word in text_lower:
            extracted.append((label, word.upper()))

    # 4. Capture ANY Numbers (Even small ones)
    # The previous code failed because it looked for 5+ digits.
    # Now we capture distinct numbers to see dates, times, amounts.
    numbers = re.findall(r'\d+', text)
    for n in numbers:
        if len(n) >= 10: label = "Phone/Account"
        elif len(n) >= 4: label = "OTP/PIN/ID"
        else: label = "Numeric Detail"
        extracted.append((label, n))

    # Save to DB (Avoid duplicates in the same session ideally, but for now just log all)
    if extracted:
        with sqlite3.connect(DB_NAME) as conn:
            for type_, value in extracted:
                # Check for duplicates to keep DB clean
                exists = conn.execute("SELECT 1 FROM evidence WHERE session_id=? AND value=?", (sid, value)).fetchone()
                if not exists:
                    conn.execute("INSERT INTO evidence (session_id, type, value, timestamp) VALUES (?, ?, ?, ?)",
                                 (sid, type_, value, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            logger.info(f"🚨 EVIDENCE CAPTURED: {extracted}")

def get_reply(text, persona_name):
    char = CHARACTERS[persona_name]
    text_lower = text.lower()
    
    if any(w in text_lower for w in ["police", "jail", "block", "urgent"]):
        return char['responses']['threat']
    if any(w in text_lower for w in ["money", "pay", "cash", "bank"]):
        return char['responses']['money']
    if any(w in text_lower for w in ["otp", "code", "pin", "card"]):
        return char['responses']['data']
    
    return char['responses']['fallback']

# --- 4. ENDPOINTS ---
@app.api_route("/{path_name:path}", methods=["GET", "POST"])
async def catch_all(request: Request, path_name: str, bg_tasks: BackgroundTasks):
    
    # --- A. VIEW EVIDENCE ---
    if "evidence" in path_name:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.execute("SELECT type, value, timestamp, session_id FROM evidence ORDER BY id DESC LIMIT 50")
            data = [{"type": r[0], "value": r[1], "time": r[2], "session": r[3]} for r in cursor.fetchall()]
            return {"status": "success", "count": len(data), "captured_evidence": data}

    # --- B. VIEW HISTORY (GLOBAL FEED) ---
    if "history" in path_name:
        with sqlite3.connect(DB_NAME) as conn:
            parts = path_name.split("/")
            sid = parts[-1] if len(parts) > 0 and parts[-1] != "history" else None

            if sid:
                cursor = conn.execute("SELECT role, message, timestamp FROM messages WHERE session_id=? ORDER BY id ASC", (sid,))
                msgs = [{"role": r[0], "message": r[1], "time": r[2]} for r in cursor.fetchall()]
                return {"status": "success", "mode": "SINGLE_SESSION", "session_id": sid, "conversation": msgs}
            else:
                cursor = conn.execute("SELECT session_id, role, message, timestamp FROM messages ORDER BY id DESC LIMIT 50")
                msgs = [{"session": r[0], "role": r[1], "message": r[2], "time": r[3]} for r in cursor.fetchall()]
                return {"status": "success", "mode": "GLOBAL_FEED", "recent_activity": msgs}

    # --- C. DASHBOARD ---
    if "dashboard" in path_name:
        with sqlite3.connect(DB_NAME) as conn:
            total_msgs = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            total_evidence = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
            return {"status": "success", "stats": {"messages": total_msgs, "evidence": total_evidence}}

    if request.method == "GET":
        return {"status": "ONLINE", "system": "Sentinel Hyper-Greedy"}

    # --- D. CHAT HANDLER ---
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
            cursor = conn.execute("SELECT persona FROM sessions WHERE id=?", (sid,))
            row = cursor.fetchone()
            if row:
                persona = row[0]
            else:
                persona = random.choice(list(CHARACTERS.keys()))
                conn.execute("INSERT INTO sessions (id, persona, start_time) VALUES (?, ?, ?)", 
                             (sid, persona, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()

        # 2. Reply
        reply = get_reply(user_text, persona)

        # 3. Save & Extract
        save_message(sid, "scammer", user_text)
        save_message(sid, "agent", reply)
        bg_tasks.add_task(extract_evidence, sid, user_text)

        return {"status": "success", "reply": reply}

    except Exception as e:
        logger.error(f"Error: {e}")
        return {"status": "error", "reply": "System Error"}
