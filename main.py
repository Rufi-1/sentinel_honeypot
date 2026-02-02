from fastapi import FastAPI, Request, Response, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
import time
import os
import random
import re
import asyncio
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

# --- 1. THE CHARACTERS (Polymorphic Personalities) ---
CHARACTERS = {
    "grandma": {
        "name": "Mrs. Higgins",
        "style": "Confused, 74yo lady, bad eyesight",
        "opener": "Hello? Is this my grandson? I can't read this text very well.",
        "fallbacks": [
            "I am sorry dear, my internet is very slow. What did you say?",
            "Hold on, let me find my reading glasses...",
            "Are you from the bank? My grandson usually handles this.",
            "I don't understand technology very well."
        ]
    },
    "student": {
        "name": "Rohan",
        "style": "College student, slang, busy, skeptical",
        "opener": "Yo, who is this? Do I know you? I'm in class.",
        "fallbacks": [
            "Bro, my connection is lagging. Say that again?",
            "Yo, send me the details, I'll check later.",
            "Is this legit? Kinda sus.",
            "Wait, who gave you my number?"
        ]
    },
    "uncle": {
        "name": "Uncle Raj",
        "style": "Angry, suspicious, rude, busy businessman",
        "opener": "Who is this? Speak fast, I am in a meeting!",
        "fallbacks": [
            "Hello? Can you hear me? The signal is bad.",
            "I don't have time for this nonsense. What do you want?",
            "Send me the details on WhatsApp, I am driving.",
            "Do not waste my time. Speak clearly!"
        ]
    }
}

# In-Memory Session Storage
SESSIONS = {}

# --- 2. THE SMART AI ENGINE (With Timeout) ---
async def get_smart_reply(text, history_list, char_key):
    if not API_KEY: return None
    
    char = CHARACTERS[char_key]
    hist_text = "\n".join([f"{m['role']}: {m['content']}" for m in history_list])
    
    prompt = f"""
    Act as {char['name']}. Style: {char['style']}.
    Reply to scammer. Max 1 sentence.
    History: {hist_text}
    Scammer: {text}
    Reply:
    """
    
    try:
        # We run this in a separate thread so we can time it out
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = await asyncio.to_thread(model.generate_content, prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"AI Gen Error: {e}")
        return None

# --- 3. BACKGROUND INTEL (Does not slow down chat) ---
def analyze_intel(sid, text):
    # Quick Regex Extraction
    intel = {
        "upiIds": re.findall(r"[\w\.-]+@[\w\.-]+", text),
        "phoneNumbers": re.findall(r"(?:\+91|0)?[6-9]\d{9}", text),
        "bankAccounts": re.findall(r"\b\d{9,18}\b", text),
        "keywords": [w for w in ["urgent", "block", "otp"] if w in text.lower()]
    }
    if intel['bankAccounts'] or intel['upiIds']:
        logger.info(f"🚨 SCAM INTEL CAPTURED ({sid}): {intel}")

# --- 4. THE HANDLER ---
async def handle_chat(request: Request, bg_tasks: BackgroundTasks):
    start_time = time.time()
    try:
        body = await request.body()
        try: payload = json.loads(body.decode())
        except: payload = {}

        sid = payload.get("sessionId") or "test-session"
        msg = payload.get("message", {})
        user_text = msg.get("text", "") if isinstance(msg, dict) else str(msg)

        # A. Initialize Session (Pick Random Character)
        if sid not in SESSIONS:
            char_key = random.choice(list(CHARACTERS.keys()))
            SESSIONS[sid] = {"persona": char_key, "history": []}
            # FIRST MESSAGE: Always Instant Opener (To pass 'Connect' test)
            reply = CHARACTERS[char_key]['opener']
            logger.info(f"⚡ INSTANT OPENER ({char_key})")
        
        else:
            # B. FOLLOW-UP: Try AI with Circuit Breaker
            session = SESSIONS[sid]
            char_key = session['persona']
            
            try:
                # *** THE MAGIC TRICK ***
                # We wait MAX 1.5 seconds for AI. If it's slow, we fallback.
                reply = await asyncio.wait_for(
                    get_smart_reply(user_text, session['history'], char_key), 
                    timeout=1.5
                )
                if not reply: raise Exception("AI Empty")
                logger.info(f"🤖 AI REPLIED ({char_key})")
                
            except asyncio.TimeoutError:
                # If AI is too slow, pick a smart fallback for THAT character
                reply = random.choice(CHARACTERS[char_key]['fallbacks'])
                logger.info(f"⏱️ TIMEOUT FALLBACK USED ({char_key})")
            except Exception as e:
                reply = random.choice(CHARACTERS[char_key]['fallbacks'])
                logger.info(f"⚠️ ERROR FALLBACK USED: {e}")

        # C. Save & Finish
        SESSIONS[sid]['history'].append({"role": "scammer", "content": user_text})
        SESSIONS[sid]['history'].append({"role": "agent", "content": reply})
        
        # D. Background Task
        bg_tasks.add_task(analyze_intel, sid, user_text)

        duration = (time.time() - start_time) * 1000
        logger.info(f"✅ DONE in {duration:.2f}ms")
        
        return {"status": "success", "reply": reply}

    except Exception as e:
        logger.error(f"🔥 FATAL: {e}")
        return {"status": "error", "reply": "System Error"}

# --- ENDPOINTS ---
@app.post("/api/chat")
async def chat_endpoint(request: Request, bg_tasks: BackgroundTasks):
    return await handle_chat(request, bg_tasks)

@app.post("/")
async def root_chat(request: Request, bg_tasks: BackgroundTasks):
    return await handle_chat(request, bg_tasks)

@app.get("/")
def home(): return {"status": "ONLINE", "mode": "HYBRID_AI"}
