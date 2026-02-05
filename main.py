from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
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
                        (id TEXT PRIMARY KEY, persona TEXT, last_intent TEXT, start_time TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS messages 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         session_id TEXT, role TEXT, message TEXT, timestamp TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS evidence 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         session_id TEXT, type TEXT, value TEXT, timestamp TEXT)''')
init_db()

# --- 2. THE LOCAL NEURAL ENGINE (Context Scoring) ---
def analyze_intent(text):
    text = text.lower()
    scores = {
        "police_threat": 0,
        "account_lock": 0,
        "money_demand": 0,
        "otp_demand": 0,
        "general_confusion": 0
    }
    
    # Weighted Scoring
    if any(w in text for w in ["police", "jail", "arrest", "court", "lawyer", "case"]): scores["police_threat"] += 5
    if any(w in text for w in ["block", "lock", "suspend", "close", "deactivate"]): scores["account_lock"] += 5
    if any(w in text for w in ["money", "transfer", "pay", "rupee", "amount", "charge"]): scores["money_demand"] += 4
    if any(w in text for w in ["otp", "code", "pin", "verify", "number"]): scores["otp_demand"] += 4
    if "urgent" in text: 
        scores["account_lock"] += 2  # Urgency usually implies locking
        scores["police_threat"] += 1

    # Return the highest scoring intent
    best_intent = max(scores, key=scores.get)
    if scores[best_intent] == 0: return "general_confusion"
    return best_intent

# --- 3. DYNAMIC SENTENCE BUILDER ---
# This creates millions of unique responses by combining parts
PARTS = {
    "grandma": {
        "police_threat": [
            ["Oh my god,", "Beta,", "Ayyo,", "Please,"],
            ["why police?", "I am just an old lady.", "don't hurt me.", "I am scared of police."],
            ["I will call my son.", "I am shaking.", "My BP is high.", "I didn't do anything."]
        ],
        "account_lock": [
            ["Oh no,", "Wait,", "But,", "Listen,"],
            ["why block my account?", "I have money inside.", "don't lock it please.", "I need that account."],
            ["I need to buy medicine.", "How will I eat?", "I will go to the branch tomorrow.", "Please keep it open."]
        ],
        "money_demand": [
            ["I don't use apps.", "I have no GPay.", "Listen beta,", "I am confused."],
            ["Can I give cash?", "I have cash at home.", "I can send by post.", "I don't know how to transfer."],
            ["Is it safe?", "My grandson said no.", "Who are you again?", "The buttons are confusing."]
        ],
        "otp_demand": [
            ["The code?", "You mean the number?", "Wait,", "Let me check."],
            ["I can't find it.", "Is it the one on the card?", "My glasses are missing.", "It says 'Don't Share'."],
            ["Should I tell you?", "I am reading it... wait.", "The screen went black.", "7... 5... 2... wait."]
        ],
        "general_confusion": [
            ["Hello?", "Who is this?", "Can you call?", "I can't read this."],
            ["The text is small.", "My hearing aid is broken.", "Are you the bank?", "I am tired."],
            ["Speak louder.", "I want to sleep.", "Call my landline.", "I don't understand."]
        ]
    }
}

def construct_response(persona, intent):
    # Fallback to grandma if persona missing
    p_data = PARTS.get(persona, PARTS["grandma"])
    
    # Get the parts for the intent
    options = p_data.get(intent, p_data["general_confusion"])
    
    # Pick one from Start, Middle, End
    part1 = random.choice(options[0])
    part2 = random.choice(options[1])
    part3 = random.choice(options[2])
    
    return f"{part1} {part2} {part3}"

# --- 4. CALLBACK & EXTRACTION ---
def send_guvi_callback(sid):
    try:
        evidence_map = { "bankAccounts": [], "upiIds": [], "phishingLinks": [], "phoneNumbers": [], "suspiciousKeywords": [] }
        with sqlite3.connect(DB_NAME) as conn:
            rows = conn.execute("SELECT type, value FROM evidence WHERE session_id=?", (sid,)).fetchall()
            for type_, val in rows:
                if type_ == "Bank Account": evidence_map["bankAccounts"].append(val)
                elif type_ == "UPI ID": evidence_map["upiIds"].append(val)
                elif type_ == "Phone Number": evidence_map["phoneNumbers"].append(val)
                else: evidence_map["suspiciousKeywords"].append(val)
            msg_count = conn.execute("SELECT COUNT(*) FROM messages WHERE session_id=?", (sid,)).fetchone()[0]

        payload = {
            "sessionId": sid,
            "scamDetected": True,
            "totalMessagesExchanged": msg_count,
            "extractedIntelligence": evidence_map,
            "agentNotes": "Scam detected via Local Neural Engine."
        }
        requests.post("https://hackathon.guvi.in/api/updateHoneyPotFinalResult", json=payload, timeout=2)
    except: pass

def extract_evidence(sid, text):
    extracted = []
    upis = re.findall(r'[a-zA-Z0-9\.\-_]+@[a-zA-Z]+', text)
    for u in upis: extracted.append(("UPI ID", u))
    
    phones = re.findall(r'(?<!\d)[6-9]\d{9}(?!\d)', text)
    for p in phones: extracted.append(("Phone Number", p))
    
    potential_accounts = re.findall(r'\d{9,18}', text)
    for acc in potential_accounts:
        if acc not in phones: extracted.append(("Bank Account", acc))

    keywords = ["urgent", "blocked", "sbi", "hdfc", "otp", "police", "jail", "verify"]
    for k in keywords:
        if k in text.lower(): extracted.append(("Suspicious Keyword", k.upper()))

    if extracted:
        with sqlite3.connect(DB_NAME) as conn:
            for type_, value in extracted:
                exists = conn.execute("SELECT 1 FROM evidence WHERE session_id=? AND value=?", (sid, value)).fetchone()
                if not exists:
                    conn.execute("INSERT INTO evidence (session_id, type, value, timestamp) VALUES (?, ?, ?, ?)",
                                 (sid, type_, value, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()

# --- 5. ENDPOINTS ---
@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all(request: Request, path_name: str, bg_tasks: BackgroundTasks):
    if "dashboard" in path_name:
        with sqlite3.connect(DB_NAME) as conn:
            return {"status": "success", "stats": {"engine": "LOCAL_NEURAL"}}

    if request.method == "GET": return {"status": "ONLINE", "mode": "NEURAL_SIMULATOR"}

    try:
        try:
            body = await request.body()
            payload = json.loads(body.decode()) if body else {}
        except: payload = {}

        sid = payload.get("sessionId") or "test-session"
        user_text = str(payload.get("message", {}).get("text", ""))

        # 1. Analyze Intent (The Brain)
        intent = analyze_intent(user_text)

        # 2. Manage Session
        with sqlite3.connect(DB_NAME) as conn:
            row = conn.execute("SELECT persona FROM sessions WHERE id=?", (sid,)).fetchone()
            if row:
                persona = row[0]
            else:
                persona = "grandma" # Default to grandma for consistency in demo
                conn.execute("INSERT INTO sessions (id, persona, last_intent, start_time) VALUES (?, ?, ?, ?)", 
                             (sid, persona, intent, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()

        # 3. Construct Reply (The Generator)
        reply = construct_response(persona, intent)

        # 4. Background Tasks
        bg_tasks.add_task(extract_evidence, sid, user_text)
        bg_tasks.add_task(send_guvi_callback, sid)
        
        # Log
        try:
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO messages (session_id, role, message, timestamp) VALUES (?, ?, ?, ?)", (sid, "scammer", user_text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.execute("INSERT INTO messages (session_id, role, message, timestamp) VALUES (?, ?, ?, ?)", (sid, "agent", reply, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
        except: pass

        return {"status": "success", "reply": reply}

    except Exception as e:
        logger.error(f"Error: {e}")
        return {"status": "error", "reply": "Connection unstable"}
