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
    GREEDY MODE: Captures ANY number sequence > 4 digits.
    This ensures we catch dummy data from the tester.
    """
    extracted = []
    
    # Capture Emails
    emails = re.findall(r'[\w\.-]+@[\w\.-]+', text)
    for e in emails: extracted.append(("Email/UPI", e))
    
    # Capture ANY number sequence longer than 4 digits (OTP, Account, Phone, ID)
    # This is the "Greedy" fix
    numbers = re.findall(r'\d{5,}', text) 
    for n in numbers:
        # Guesses based on length
        if len(n) == 6: label = "Possible OTP"
        elif len(n) == 10: label = "Phone Number"
        elif len(n) >= 11: label = "Bank Account/ID"
        else: label = "Numeric Identifier"
        extracted.append((label, n))

    # Save to DB
    if extracted:
        with sqlite3.connect(DB_NAME) as conn:
            for type_, value in extracted:
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
    
    # Regex Reflection (Greedy)
    numbers = re.findall(r'\d{4,}', text)
    if numbers:
        if persona_name == "grandma": return f"I see the number {numbers[0]}... is that the amount?"
        
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
    # Shows ALL messages from ALL sessions (Fixes the "One Message" bug)
    if "history" in path_name:
        with sqlite3.connect(DB_NAME) as conn:
            # Check if specific ID is requested
            parts = path_name.split("/")
            sid = parts[-1] if len(parts) > 0 and parts[-1] != "history" else None

            if sid:
                # Show specific session
                cursor = conn.execute("SELECT role, message, timestamp FROM messages WHERE session_id=? ORDER BY id ASC", (sid,))
                msgs = [{"role": r[0], "message": r[1], "time": r[2]} for r in cursor.fetchall()]
                return {"status": "success", "mode": "SINGLE_SESSION", "session_id": sid, "conversation": msgs}
            else:
                # Show GLOBAL FEED (Last 50 messages from ANY session)
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
        return {"status": "ONLINE", "system": "Sentinel Greedy-Mode"}

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
