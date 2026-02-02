from fastapi import FastAPI, Request, Response, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
import time
import os
import random
import re
import requests
import google.generativeai as genai

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

API_KEY = os.environ.get("GEMINI_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- IN-MEMORY DATABASE ---
# Stores { "session_123": { "persona": "grandma", "intel": {}, "history": [...] } }
SESSIONS = {}

CHARACTERS = {
    "grandma": {
        "opener": "Hello? Is this my grandson? I can't read this text very well.",
        "style": "Confused, 74yo lady"
    },
    "student": {
        "opener": "Yo, who is this? Do I know you?",
        "style": "Skeptical student"
    },
    "uncle": {
        "opener": "Who gave you this number? Speak fast.",
        "style": "Angry uncle"
    }
}

# --- LOGIC ---
def extract_intel(text):
    return {
        "upiIds": re.findall(r"[\w\.-]+@[\w\.-]+", text),
        "phishingLinks": re.findall(r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+", text),
        "phoneNumbers": re.findall(r"(?:\+91|0)?[6-9]\d{9}", text),
        "bankAccounts": re.findall(r"\b\d{9,18}\b", text),
        "suspiciousKeywords": [w for w in ["urgent", "block", "otp", "verify"] if w in text.lower()]
    }

def generate_ai_reply(text, history_list, char_name):
    if not API_KEY: return "I am having connection issues."
    
    hist_text = "\n".join([f"{m['role']}: {m['content']}" for m in history_list])
    prompt = f"""
    Act as {char_name}. Reply to the scammer. Keep it short.
    History: {hist_text}
    Scammer: {text}
    Reply:
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        return response.text.strip()
    except:
        return "I am confused. Say again?"

async def handle_chat(request: Request, bg_tasks: BackgroundTasks):
    try:
        body_bytes = await request.body()
        try: payload = json.loads(body_bytes.decode())
        except: payload = {}

        sid = payload.get("sessionId") or "test-session"
        msg = payload.get("message", {})
        user_text = msg.get("text", "") if isinstance(msg, dict) else str(msg)

        # 1. Initialize Session
        if sid not in SESSIONS:
            persona = random.choice(list(CHARACTERS.keys()))
            SESSIONS[sid] = {
                "persona": persona,
                "history": [],
                "intel": {"upiIds": [], "bankAccounts": [], "phoneNumbers": [], "suspiciousKeywords": []}
            }
            # Instant Opener
            reply = CHARACTERS[persona]['opener']
        else:
            # AI Reply
            sess = SESSIONS[sid]
            reply = generate_ai_reply(user_text, sess['history'], sess['persona'])

        # 2. Save History
        SESSIONS[sid]['history'].append({"role": "scammer", "content": user_text})
        SESSIONS[sid]['history'].append({"role": "agent", "content": reply})

        # 3. Update Intel
        new_intel = extract_intel(user_text)
        current_intel = SESSIONS[sid]['intel']
        for k, v in new_intel.items():
            current_intel[k] = list(set(current_intel.get(k, []) + v))

        # 4. Trigger Callback (Simulated)
        if current_intel['bankAccounts'] or current_intel['upiIds']:
            logger.info(f"🚨 SCAM DETECTED! Captured: {current_intel}")
            # requests.post("https://hackathon.guvi.in/...", json=...) 

        return {"status": "success", "reply": reply}
    except Exception as e:
        return {"status": "error", "reply": "System Error"}

# --- ENDPOINTS ---
@app.post("/api/chat")
async def chat_endpoint(request: Request, bg_tasks: BackgroundTasks):
    return await handle_chat(request, bg_tasks)

@app.post("/")
async def root_chat(request: Request, bg_tasks: BackgroundTasks):
    return await handle_chat(request, bg_tasks)

# --- NEW: DASHBOARD VIEWER ---
@app.get("/api/view/{session_id}")
def view_session(session_id: str):
    if session_id in SESSIONS:
        return SESSIONS[session_id]
    return {"error": "Session not found. Chat first!"}

@app.get("/")
def home(): return {"status": "ONLINE"}
