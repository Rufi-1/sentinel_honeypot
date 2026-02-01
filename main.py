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
import google.generativeai as genai # <--- CHANGED THIS IMPORT

# --- 1. CONFIGURATION ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

# HARDCODE KEY HERE IF RENDER KEEPS FAILING
API_KEY = os.environ.get("GEMINI_API_KEY") 

# CONFIGURE AI (The Stable Way)
if API_KEY:
    genai.configure(api_key=API_KEY)
else:
    logger.error("❌ API KEY MISSING")

app = FastAPI()

# --- 2. OPEN ACCESS (CORS) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    logger.info(f"🔔 KNOCK: {request.method} {request.url}")
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        logger.info(f"✅ RESP: {response.status_code} ({process_time:.2f}ms)")
        return response
    except Exception as e:
        logger.error(f"🔥 CRASH: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})

# --- 3. DATABASE ---
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

# --- 4. LOGIC ---
CHARACTERS = {
    "grandma": {"name": "Mrs. Higgins", "role": "Grandma", "style": "Confused", "strategy": "Act confused"},
    "student": {"name": "Rohan", "role": "Student", "style": "Bro, slang", "strategy": "Troll"}
}

def generate_reply(incoming, history, pid):
    if not API_KEY: return "I am having connection issues."
    
    char = CHARACTERS.get(pid, CHARACTERS['grandma'])
    hist_text = "\n".join([f"{m['sender']}: {m['text']}" for m in history])
    
    prompt = f"""
    Act as {char['name']}. Style: {char['style']}.
    Reply to scammer. Keep it short.
    History: {hist_text}
    Scammer: {incoming}
    Reply:
    """
    try:
        # USE STABLE MODEL CALL
        model = genai.GenerativeModel('gemini-2.5-flash')
        res = model.generate_content(prompt)
        return res.text.strip()
    except Exception as e:
        logger.error(f"AI Error: {e}")
        return "I am confused. Say again?"

def extract_intel(text):
    return {
        "upiIds": re.findall(r"[\w\.-]+@[\w\.-]+", text),
        "phishingLinks": re.findall(r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+", text),
        "phoneNumbers": re.findall(r"(?:\+91|0)?[6-9]\d{9}", text),
        "bankAccounts": re.findall(r"\b\d{9,18}\b", text),
        "suspiciousKeywords": ["urgent"] if "urgent" in text.lower() else []
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
            logger.info(f"🚀 Callback: {payload}")
            requests.post("https://hackathon.guvi.in/api/updateHoneyPotFinalResult", json=payload, timeout=2)
    except Exception as e:
        logger.error(f"BG Error: {e}")

# --- 5. ENDPOINTS ---

@app.head("/")
@app.head("/api/chat")
def ping(): 
    return Response(status_code=200)

@app.get("/")
def home():
    return {"status": "ONLINE", "system": "Sentinel Polymorphic Node"}

@app.post("/api/chat")
async def chat(request: Request, bg_tasks: BackgroundTasks):
    try:
        body = await request.body()
        logger.info(f"📥 RAW: {body.decode()}")
        try: payload = json.loads(body.decode())
        except: payload = {}

        sid = payload.get("sessionId") or payload.get("session_id") or "test"
        msg = payload.get("message", {})
        text = msg.get("text", "Hello") if isinstance(msg, dict) else str(msg)

        session = get_session(sid)
        if not session:
            pid = random.choice(list(CHARACTERS.keys()))
            create_session(sid, pid)
            session = {"persona_id": pid}

        reply = generate_reply(text, get_history(sid), session['persona_id'])
        bg_tasks.add_task(bg_task, sid, text, reply)

        return {"status": "success", "reply": reply}

    except Exception as e:
        logger.error(f"🔥 FATAL: {e}")
        return {"status": "error", "reply": "System Error"}
