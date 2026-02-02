from fastapi import FastAPI, Request, Response, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
import time
import os
import random
import re

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI()

# --- 1. ALLOW EVERYTHING (CORS) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 2. THE BRAIN (Heuristic Expert System) ---
CHARACTERS = {
    "grandma": {
        "opener": "Hello? Is this my grandson? I can't read this text very well.",
        "fallback": "I am sorry dear, I don't understand. Can you call my landline?"
    },
    "student": {
        "opener": "Yo, who is this? Do I know you? I'm in a lecture.",
        "fallback": "Bro, you're making no sense. Text me later."
    },
    "uncle": {
        "opener": "Who gave you this number? Speak fast, I am busy.",
        "fallback": "State your business clearly or I am blocking this number."
    }
}

SCENARIO_DB = {
    ("money", "transfer", "cash", "rupees"): ["I have cash in the tin box. Do you want that?", "I'm broke bro.", "I do not transfer money to strangers."],
    ("bank", "sbi", "hdfc", "account"): ["Which bank? The one near the market?", "I don't have a bank account lol.", "I will visit the branch personally."],
    ("otp", "code", "pin"): ["Is the code the numbers on the back?", "Nice try scammer.", "NEVER ask for OTP. Reporting you."],
    ("police", "jail", "block"): ["Police?! I didn't steal anything!", "Lol police? For what?", "I know the Commissioner. Back off."],
    ("urgent", "immediate"): ["Why are you shouting? You are scaring me!", "Chill, why the rush?", "Do not pressure me."]
}

SESSIONS = {}

def get_heuristic_reply(text, char_key):
    # 1. Check Database
    text_lower = text.lower()
    for keywords, responses in SCENARIO_DB.items():
        if any(k in text_lower for k in keywords):
            if char_key == "grandma": return responses[0]
            elif char_key == "student": return responses[1]
            elif char_key == "uncle": return responses[2]
    
    # 2. Heuristic Fallback
    if "?" in text:
        if char_key == "grandma": return "I am not sure... why do you ask?"
        if char_key == "student": return "Why do you need to know?"
        if char_key == "uncle": return "I ask the questions here."
        
    return CHARACTERS[char_key]['fallback']

# --- 3. THE UNIVERSAL VACUUM (Catch-All Route) ---
# This matches ANY path and ANY method (GET, POST, OPTIONS, PUT)
@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"])
async def catch_all(request: Request, path_name: str, bg_tasks: BackgroundTasks):
    start_time = time.time()
    method = request.method
    
    # LOGGING: Finally see what the Tester is doing!
    logger.info(f"🔔 HIT: {method} /{path_name}")

    # A. HANDLE CORSIOPTIONS (The Handshake)
    if method == "OPTIONS":
        return Response(status_code=200)

    # B. HANDLE GET (The Ping)
    if method == "GET":
        return {"status": "ONLINE", "mode": "UNIVERSAL_CATCH_ALL"}

    # C. HANDLE POST (The Chat)
    try:
        # 1. Try to read body
        body_bytes = await request.body()
        body_str = body_bytes.decode()
        logger.info(f"📥 RAW BODY: {body_str}")

        # 2. Parse JSON (Safely)
        try: payload = json.loads(body_str)
        except: payload = {}

        sid = payload.get("sessionId") or "test-session"
        msg = payload.get("message", {})
        # Handle cases where message is just a string or a dict
        if isinstance(msg, dict):
            user_text = msg.get("text", "")
        else:
            user_text = str(msg)
            
        # 3. RUN LOGIC
        if sid not in SESSIONS:
            char_key = random.choice(list(CHARACTERS.keys()))
            SESSIONS[sid] = {"persona": char_key}
            reply = CHARACTERS[char_key]['opener']
            logger.info(f"⚡ NEW SESSION: {char_key}")
        else:
            char_key = SESSIONS[sid]['persona']
            reply = get_heuristic_reply(user_text, char_key)
            logger.info(f"🧠 REPLY generated for {char_key}")

        # 4. RETURN (Fast!)
        duration = (time.time() - start_time) * 1000
        logger.info(f"✅ DONE in {duration:.2f}ms")
        
        return {"status": "success", "reply": reply}

    except Exception as e:
        logger.error(f"🔥 CRASH: {e}")
        # Even if we crash, return valid JSON so the tester doesn't error
        return {"status": "error", "reply": "System Error"}
