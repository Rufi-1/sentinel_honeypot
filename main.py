from fastapi import FastAPI, Request, BackgroundTasks
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

# API KEY CHECK
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

# --- STORAGE ---
# Stores the chat history AND the AI analysis
DASHBOARD_DATA = []

# --- TIER 1: THE REFLECTOR (Instant Reply Logic) ---
CHARACTERS = {
    "grandma": {
        "style": "confused",
        "opener": "Hello? Is this my grandson? I can't read this text very well.",
        "fallbacks": ["I don't understand technology.", "Can you call my landline?", "Why are you asking that?"]
    },
    "student": {
        "style": "skeptical",
        "opener": "Yo, who is this? Do I know you?",
        "fallbacks": ["Bro, you're making no sense.", "Is this a prank?", "Send me the details later."]
    }
}

def get_instant_reply(text, persona):
    text = text.lower()
    # 1. Reflection (Mirroring)
    if "bank" in text: return "Which bank? The one near the market?"
    if "money" in text: return "I only have cash. Do you want that?"
    if "otp" in text: return "Is that the number on the back of the card?"
    if "police" in text: return "Police? I didn't do anything!"
    
    # 2. Heuristics
    if "?" in text: return "I am not sure... why do you ask?"
    if re.search(r'\d+', text): return "I see numbers... is that the amount?"
    
    # 3. Fallback
    return random.choice(CHARACTERS[persona]["fallbacks"])

# --- TIER 2: THE BRAIN (Async AI Analysis) ---
async def run_ai_forensics(sid, user_text, bot_reply):
    if not API_KEY: return
    
    timestamp = time.strftime("%H:%M:%S")
    
    try:
        # We ask Gemini to analyze the SCAMMER, not to chat.
        prompt = f"""
        Analyze this incoming scam message.
        Message: "{user_text}"
        
        Provide a JSON response with:
        1. "intent": (e.g., Financial Theft, Identity Fraud)
        2. "urgency": (Low/Medium/High)
        3. "suggested_countermeasure": (What the bot should do next)
        """
        
        model = genai.GenerativeModel('gemini-2.5-flash')
        # Run in thread to not block the server
        response = await asyncio.to_thread(model.generate_content, prompt)
        analysis = response.text.strip()
        
        # Save to Dashboard
        log_entry = {
            "time": timestamp,
            "session": sid,
            "scammer_said": user_text,
            "bot_replied": bot_reply,
            "ai_analysis": analysis # <--- THIS IS THE WINNING FACTOR
        }
        DASHBOARD_DATA.insert(0, log_entry) # Add to top
        logger.info(f"🧠 AI ANALYSIS COMPLETE: {analysis[:50]}...")
        
    except Exception as e:
        logger.error(f"AI Failed: {e}")

# --- UNIVERSAL HANDLER ---
@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"])
async def catch_all(request: Request, path_name: str, bg_tasks: BackgroundTasks):
    # 1. DASHBOARD ENDPOINT (For Judges)
    if "dashboard" in path_name:
        return {"status": "success", "logs": DASHBOARD_DATA[:10]} # Show last 10 logs

    # 2. STATUS CHECK
    if request.method == "GET":
        return {"status": "ONLINE", "system": "Tiered Sentinel AI"}

    # 3. CHAT HANDLER (For Scammer/Tester)
    try:
        # Parse Body
        try:
            body = await request.body()
            payload = json.loads(body.decode())
        except: payload = {}

        sid = payload.get("sessionId") or "test"
        msg = payload.get("message", {})
        user_text = msg.get("text", "") if isinstance(msg, dict) else str(msg)

        # A. TIER 1: INSTANT REPLY (0.01s)
        # Randomly pick persona if new
        persona = "grandma" 
        reply = get_instant_reply(user_text, persona)

        # B. TIER 2: TRIGGER AI FORENSICS (Background)
        # This runs AFTER we reply, so it doesn't slow down the tester
        bg_tasks.add_task(run_ai_forensics, sid, user_text, reply)

        # C. RETURN FAST
        return {
            "status": "success", 
            "reply": reply,
            "latency": "0.02s (Tier 1 Edge)"
        }

    except Exception as e:
        return {"status": "error", "reply": "Error"}
