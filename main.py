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
                        (id TEXT PRIMARY KEY, persona TEXT, used_replies TEXT, start_time TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS messages 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         session_id TEXT, role TEXT, message TEXT, timestamp TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS evidence 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         session_id TEXT, type TEXT, value TEXT, timestamp TEXT)''')
init_db()

# --- 2. ADVANCED GENERATIVE PERSONAS ---
# Uses {placeholders} to inject Scammer's own words back at them.
CHARACTERS = {
    "grandma": {
        "style": "confused",
        "templates": {
            "money": [
                "I don't have online banking... can I give cash to the postman?",
                "My grandson said never to send money to {number}. Is that you?",
                "I have some rupees in a biscuit tin. Do you want me to mail it?",
                "Why does {bank} need me to pay? I thought I had a free account.",
                "I am pressing the buttons but nothing is happening.",
                "Can you wait? I need to find my reading glasses to read the numbers."
            ],
            "threat": [
                "Please don't block me! I need this phone to call my doctor.",
                "Police? Oh my god, I am an old lady, please don't hurt me!",
                "I am shaking right now... what did I do wrong?",
                "Why are you shouting at me via text? I am trying my best.",
                "I will call my son, he is a lawyer. He will explain to you."
            ],
            "data": [
                "Is the OTP the number on the back of the card? It says 7... 2...",
                "I see a code {otp}... is that the one?",
                "Wait, my screen went black. Hello? Are you still there?",
                "I don't know where the OTP is. Is it in the letter?",
                "It says 'Do not share this code'. Should I still give it to you?"
            ],
            "fallback": [
                "I am very confused. Can you call my landline instead?",
                "Who is this again? My memory is not what it used to be.",
                "Hello? The line is very bad.",
                "I think I will go to the bank tomorrow to ask them directly."
            ]
        }
    },
    "uncle": {
        "style": "aggressive",
        "templates": {
            "money": [
                "I do not transfer money to strangers. Send an official invoice to my office.",
                "Why should I send money to {number}? That looks like a personal number!",
                "I will visit the {bank} branch personally to slap you.",
                "Do you think I am stupid? I know how banking works.",
                "I am not paying a single rupee until I see a signed letter."
            ],
            "threat": [
                "Do not threaten me! I know the Commissioner personally.",
                "I am recording this chat. You will be in jail by tonight.",
                "Go ahead, block it. I will sue the bank for damages.",
                "I am tracking your IP address right now.",
                "You are making a very big mistake threatening a government official."
            ],
            "data": [
                "NEVER ask for OTP. That is rule number one.",
                "I am reporting {number} to the Cyber Crime cell immediately.",
                "I will not share confidential info over an unsecured chat.",
                "Block me if you want. I don't care.",
                "Send me your employee ID card first."
            ],
            "fallback": [
                "State your business clearly or I am hanging up.",
                "Stop wasting my time. I have a meeting.",
                "This smells like a scam. I am verifying you now.",
                "Speak properly. Who is your supervisor?"
            ]
        }
    }
}
# (You can add 'student' back here following the same pattern if needed, keeping it simple for code length)

# --- 3. INTELLIGENCE ENGINE ---
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
    extracted = []
    
    # Precise Extraction
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

def generate_smart_reply(sid, text, persona_name):
    char = CHARACTERS.get(persona_name, CHARACTERS["uncle"]) # Default to Uncle if missing
    text_lower = text.lower()
    
    # 1. Extract Context (The "Smart" Part)
    # We find what the scammer is talking about to inject into our reply
    bank_match = re.search(r'(sbi|hdfc|icici|axis|bank)', text_lower)
    bank_name = bank_match.group(0).upper() if bank_match else "the bank"
    
    num_match = re.search(r'\d{10}', text)
    phone_num = num_match.group(0) if num_match else "that number"
    
    otp_match = re.search(r'\d{4,6}', text)
    fake_otp = str(random.randint(1000, 9999))
    
    # 2. Determine Intent
    category = "fallback"
    if any(w in text_lower for w in ["police", "jail", "block", "lock", "ban"]): category = "threat"
    elif any(w in text_lower for w in ["money", "pay", "transfer", "rupees"]): category = "money"
    elif any(w in text_lower for w in ["otp", "code", "pin", "verify"]): category = "data"
    
    # 3. Get History (Anti-Repetition)
    with sqlite3.connect(DB_NAME) as conn:
        row = conn.execute("SELECT used_replies FROM sessions WHERE id=?", (sid,)).fetchone()
        used_replies = json.loads(row[0]) if row and row[0] else []

    # 4. Select Template (Filter out used ones)
    templates = char['templates'][category]
    available_templates = [t for t in templates if t not in used_replies]
    
    # If we ran out of new lines, reset memory (rare case)
    if not available_templates: 
        available_templates = templates
        used_replies = [] 

    selected_template = random.choice(available_templates)
    
    # 5. Fill Slots (The "AI" Feel)
    reply = selected_template.replace("{bank}", bank_name).replace("{number}", phone_num).replace("{otp}", fake_otp)
    
    # 6. Save Memory
    used_replies.append(selected_template) # Save the *template* not the filled string to avoid near-duplicates
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("UPDATE sessions SET used_replies=? WHERE id=?", (json.dumps(used_replies), sid))
        conn.commit()
        
    return reply

# --- 4. ENDPOINTS ---
@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all(request: Request, path_name: str, bg_tasks: BackgroundTasks):
    
    # Dashboard
    if "dashboard" in path_name:
        with sqlite3.connect(DB_NAME) as conn:
            return {"status": "success", "stats": {"active": True}}

    if request.method == "GET": return {"status": "ONLINE", "mode": "AGENTIC_V5"}

    try:
        try:
            body = await request.body()
            payload = json.loads(body.decode()) if body else {}
        except: payload = {}

        sid = payload.get("sessionId") or "test-session"
        msg = payload.get("message", {})
        user_text = msg.get("text", "") if isinstance(msg, dict) else str(msg)

        # Session
        with sqlite3.connect(DB_NAME) as conn:
            row = conn.execute("SELECT persona FROM sessions WHERE id=?", (sid,)).fetchone()
            if row:
                persona = row[0]
            else:
                persona = random.choice(list(CHARACTERS.keys()))
                conn.execute("INSERT INTO sessions (id, persona, used_replies, start_time) VALUES (?, ?, ?, ?)", 
                             (sid, persona, json.dumps([]), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()

        # Reply
        reply = generate_smart_reply(sid, user_text, persona)

        # Save & Callback
        bg_tasks.add_task(extract_evidence, sid, user_text)
        bg_tasks.add_task(send_guvi_callback, sid)
        
        # Log to DB
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
