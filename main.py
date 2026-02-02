from fastapi import FastAPI, Request, Response, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import json
import logging
import time
import os
import re
import random
import sqlite3
import requests
import google.generativeai as genai

# --- 1. CONFIGURATION ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

API_KEY = os.environ.get("GEMINI_API_KEY") 
if API_KEY:
    genai.configure(api_key=API_KEY)

app = FastAPI()

# --- 2. CORS (Open Access) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 3. DATABASE MODULE ---
DB_NAME = "honeypot.db"
def init_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sessions 
                 (session_id TEXT PRIMARY KEY, is_scam BOOLEAN, msg_count INTEGER, persona_id TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages 
                 (session_id TEXT, sender TEXT, text TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS intelligence 
                 (session_id TEXT PRIMARY KEY, data TEXT)''')
    conn.commit()
    conn.close()

init_db()

def get_session(sid):
    with sqlite3.connect(DB_NAME, check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM sessions WHERE session_id=?", (sid,))
        row = c.fetchone()
        if row: return {"session_id": row[0], "is_scam": row[1], "msg_count": row[2], "persona_id": row[3]}
    return None

def create_session(sid, pid):
    with sqlite3.connect(DB_NAME, check_same_thread=False) as conn:
        conn.execute("INSERT OR IGNORE INTO sessions VALUES (?, ?, ?, ?)", (sid, False, 0, pid))
        empty_intel = json.dumps({"bankAccounts": [], "upiIds": [], "phishingLinks": [], "phoneNumbers": [], "suspiciousKeywords": []})
        conn.execute("INSERT OR IGNORE INTO intelligence VALUES (?, ?)", (sid, empty_intel))

def get_history(sid):
    with sqlite3.connect(DB_NAME, check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("SELECT sender, text FROM messages WHERE session_id=?", (sid,))
        rows = c.fetchall()
    return [{"sender": r[0], "text": r[1]} for r in rows]

def save_message(sid, sender, text):
    with sqlite3.connect(DB_NAME, check_same_thread=False) as conn:
        conn.execute("INSERT INTO messages (session_id, sender, text) VALUES (?, ?, ?)", (sid, sender, text))

def update_intel(sid, new_data):
    with sqlite3.connect(DB_NAME, check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("SELECT data FROM intelligence WHERE session_id=?", (sid,))
        row = c.fetchone()
        current = json.loads(row[0]) if row else {}
        for k, v in new_data.items():
            current[k] = list(set(current.get(k, []) + v))
        conn.execute("UPDATE intelligence SET data=? WHERE session_id=?", (json.dumps(current), sid))
    return current

# --- 4. MULTI-CHARACTER LOGIC ---
CHARACTERS = {
    "grandma": {
        "name": "Mrs. Higgins", 
        "style": "Confused, 74 years old, bad with technology", 
        "opener": "Hello? Is this my grandson? I can't read this message clearly without my glasses."
    },
    "student": {
        "name": "Rohan", 
        "style": "College student, slang, busy with exams, skeptical", 
        "opener": "Yo, who is this? Do I know you? I'm in class right now."
    },
    "uncle": {
        "name": "Uncle Raj", 
        "style": "Angry, suspicious, asks too many questions, rude", 
        "opener": "Who gave you this number? Speak quickly, I am busy!"
    }
}

def generate_reply(incoming, history, pid):
    if not API_KEY: return "I am having connection issues."
    
    # Fallback to grandma if persona missing
    char = CHARACTERS.get(pid, CHARACTERS['grandma'])
    hist_text = "\n".join([f"{m['sender']}: {m['text']}" for m in history])
    
    prompt = f"""
    You are {char['name']}. Traits: {char['style']}.
    Task: Reply to this scammer. Keep it short (1-2 sentences).
    - Do NOT say you are an AI.
    - Act exactly like your character.
    
    Conversation History:
    {hist_text}
    
    Scammer: {incoming}
    Reply:
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        res = model.generate_content(prompt)
        return res.text.strip()
    except Exception as e:
        logger.error(f"AI Error: {e}")
        return "I am confused. Can you say that again?"

def extract_intel(text):
    return {
        "upiIds": re.findall(r"[\w\.-]+@[\w\.-]+", text),
        "phishingLinks": re.findall(r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+", text),
        "phoneNumbers": re.findall(r"(?:\+91|0)?[6-9]\d{9}", text),
        "bankAccounts": re.findall(r"\b\d{9,18}\b", text),
        "suspiciousKeywords": ["urgent", "block", "otp", "kfc", "verify"] if any(x in text.lower() for x in ["urgent", "block", "otp", "verify"]) else []
    }

def bg_task(sid, user_text, agent_text):
    try:
        save_message(sid, "scammer", user_text)
        save_message(sid, "agent", agent_text)
        intel = extract_intel(user_text + " " + agent_text)
        final_intel = update_intel(sid, intel)
        
        hist = get_history(sid)
        if final_intel['phishingLinks'] or final_intel['upiIds'] or len(hist) > 1:
            payload = {
                "sessionId": sid, "scamDetected": True,
                "totalMessagesExchanged": len(hist),
                "extractedIntelligence": final_intel, "agentNotes": "Sentinel Active"
            }
            # Fire and forget callback
            requests.post("https://hackathon.guvi.in/api/updateHoneyPotFinalResult", json=payload, timeout=1)
    except Exception as e:
        logger.error(f"BG Error: {e}")

# --- 5. ENDPOINTS ---

@app.head("/")
@app.head("/api/chat")
def ping(): return Response(status_code=200)

@app.get("/")
def home(): return {"status": "ONLINE", "characters": list(CHARACTERS.keys())}

@app.post("/api/chat")
async def chat(request: Request, bg_tasks: BackgroundTasks):
    start = time.time()
    try:
        body = await request.body()
        try: payload = json.loads(body.decode())
        except: payload = {}

        sid = payload.get("sessionId") or payload.get("session_id") or "test"
        msg = payload.get("message", {})
        text = msg.get("text", "Hello") if isinstance(msg, dict) else str(msg)

        # 1. SETUP SESSION (Randomly pick 1 of 3 characters)
        session = get_session(sid)
        if not session:
            # THIS IS WHERE THE MAGIC HAPPENS
            pid = random.choice(list(CHARACTERS.keys())) 
            create_session(sid, pid)
            session = {"persona_id": pid}
        
        current_history = get_history(sid)
        persona_id = session['persona_id']

        # 2. INSTANT REPLY (Specific to the chosen character)
        if len(current_history) == 0:
            # If randomly picked Student, says "Yo". If Grandma, says "Hello?".
            reply = CHARACTERS.get(persona_id, CHARACTERS['grandma'])['opener']
            logger.info(f"⚡ INSTANT OPENER SENT for {persona_id}")
        else:
            # 3. AI REPLY (Gemini takes over personality)
            reply = generate_reply(text, current_history, persona_id)
            logger.info(f"🤖 AI REPLY SENT for {persona_id}")

        bg_tasks.add_task(bg_task, sid, text, reply)

        process_time = (time.time() - start) * 1000
        logger.info(f"✅ DONE in {process_time:.2f}ms")
        
        return {"status": "success", "reply": reply}

    except Exception as e:
        logger.error(f"🔥 FATAL: {e}")
        return {"status": "error", "reply": "System Error"}
