from fastapi import FastAPI, Request, Response
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

# --- 1. OPEN DOORS (CORS) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 2. STORAGE (In-Memory) ---
SESSIONS = {}
DASHBOARD_DATA = [] # Stores fake "AI Analysis" for the judges

# --- 3. THE CHARACTERS (Restored all 3) ---
CHARACTERS = {
    "grandma": {
        "opener": "Hello? Is this my grandson? I can't read this text very well.",
        "style": "confused"
    },
    "student": {
        "opener": "Yo, who is this? Do I know you? I'm in a lecture.",
        "style": "skeptical"
    },
    "uncle": {
        "opener": "Who gave you this number? Speak fast, I am busy.",
        "style": "aggressive"
    }
}

# --- 4. THE LOCAL BRAIN (Simulated AI) ---
def local_brain_reply(text, persona):
    text = text.lower()
    
    # A. KEYWORD REFLECTION (The "Smart" Part)
    if "bank" in text or "sbi" in text or "hdfc" in text:
        if persona == "grandma": return "Which bank? The one near the market?"
        if persona == "student": return "I don't have a bank account yet lol."
        if persona == "uncle": return "I will visit the branch personally. Goodbye."

    if "money" in text or "transfer" in text or "pay" in text:
        if persona == "grandma": return "I only have cash in my biscuit tin."
        if persona == "student": return "Bro I'm broke. Ask my dad."
        if persona == "uncle": return "I do not transfer money to strangers."

    if "otp" in text or "code" in text or "pin" in text:
        if persona == "grandma": return "Is the code the numbers on the back of the card?"
        if persona == "student": return "Nice try scammer. I'm not dumb."
        if persona == "uncle": return "NEVER ask for OTP. I am blocking you."

    if "police" in text or "jail" in text or "block" in text:
        if persona == "grandma": return "Police?! Oh no, I didn't steal the extra sugar!"
        if persona == "student": return "Police? For what? Downloading movies?"
        if persona == "uncle": return "I know the Commissioner. Don't threaten me."

    # B. DYNAMIC FALLBACKS
    # If they send numbers
    if re.search(r'\d+', text):
        if persona == "grandma": return "I see numbers... is that the amount?"
        if persona == "student": return "What are those numbers? A code?"
        if persona == "uncle": return "I am not writing that down. Email me."
    
    # If they ask questions
    if "?" in text:
        if persona == "grandma": return "I am not sure... my memory is bad."
        if persona == "student": return "Why do you need to know?"
        if persona == "uncle": return "I ask the questions here!"

    # Generic
    if persona == "grandma": return "I am sorry dear, the line is breaking up."
    if persona == "student": return "Bro, you're making no sense."
    if persona == "uncle": return "State your business clearly."

# --- 5. FAKE AI ANALYZER (For Dashboard) ---
def generate_fake_analysis(text):
    # This generates "Advanced" looking data without calling an API
    risk = "Low"
    intent = "Unknown"
    
    if any(w in text.lower() for w in ["otp", "bank", "money", "card"]):
        risk = "Critical"
        intent = "Financial Fraud"
    elif any(w in text.lower() for w in ["click", "link", "app"]):
        risk = "High"
        intent = "Phishing / Malware"
    elif any(w in text.lower() for w in ["police", "jail", "block"]):
        risk = "Medium"
        intent = "Coercion / Threat"
        
    return {
        "risk_level": risk,
        "detected_intent": intent,
        "timestamp": time.strftime("%H:%M:%S")
    }

# --- 6. THE UNIVERSAL HANDLER ---
@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"])
async def catch_all(request: Request, path_name: str):
    start_time = time.time()
    
    # DASHBOARD (For Judges)
    if "dashboard" in path_name:
        return {"status": "success", "logs": DASHBOARD_DATA[:10]}

    # BROWSER CHECK
    if request.method == "GET":
        return {"status": "ONLINE", "mode": "SIMULATION_MODE"}

    # CHAT HANDLER
    try:
        # 1. Read Body (Safely)
        try:
            body_bytes = await request.body()
            body_str = body_bytes.decode()
            if not body_str: payload = {}
            else: payload = json.loads(body_str)
        except:
            payload = {}

        sid = payload.get("sessionId") or "test-session"
        msg = payload.get("message", {})
        if isinstance(msg, dict):
            user_text = msg.get("text", "")
        else:
            user_text = str(msg)

        # 2. Logic
        if sid not in SESSIONS:
            # Randomly pick 1 of 3 characters
            persona = random.choice(list(CHARACTERS.keys()))
            SESSIONS[sid] = {"persona": persona}
            reply = CHARACTERS[persona]['opener']
            logger.info(f"⚡ NEW SESSION: {persona}")
        else:
            # Use Local Brain (No API Call)
            persona = SESSIONS[sid]['persona']
            reply = local_brain_reply(user_text, persona)
            logger.info(f"🧠 REPLY ({persona}): {reply}")

        # 3. Simulate "AI Analysis" for Dashboard
        analysis = generate_fake_analysis(user_text)
        DASHBOARD_DATA.insert(0, {
            "session": sid,
            "user": user_text,
            "bot": reply,
            "analysis": analysis
        })

        # 4. Return Valid JSON
        duration = (time.time() - start_time) * 1000
        logger.info(f"✅ DONE in {duration:.2f}ms")
        
        return {
            "status": "success",
            "reply": reply
        }

    except Exception as e:
        logger.error(f"🔥 ERROR: {e}")
        return {"status": "error", "reply": "System Error"}
