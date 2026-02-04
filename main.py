from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
import time
import os
import random
import re
import asyncio

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

# --- 1. STORAGE ---
SESSIONS = {}
DASHBOARD_DATA = []

# --- 2. THE 5 PERSONAS (Polymorphic Engine) ---
CHARACTERS = {
    "grandma": {
        "opener": "Hello? Is this my grandson? I can't read this text very well.",
        "style": "confused",
        "responses": {
            "money": "I don't use apps... I have cash in a biscuit tin. Do you want that?",
            "threat": "Police?! Oh my god, please don't hurt me! I am an old lady.",
            "data": "Is the code the one on the back of the card? It says 7... 2... wait.",
            "fallback": "I am getting very confused. Can you just call my landline?"
        }
    },
    "student": {
        "opener": "Yo, who is this? Do I know you? I'm in a lecture.",
        "style": "skeptical",
        "responses": {
            "money": "Bro I have like ₹50 in my account. You want that?",
            "threat": "Lol police? For what? Downloading movies? Get lost.",
            "data": "You want my OTP? Send me a request on the official app first.",
            "fallback": "Bro you're making no sense. Is this a prank?"
        }
    },
    "uncle": {
        "opener": "Who gave you this number? Speak fast, I am entering a meeting.",
        "style": "aggressive",
        "responses": {
            "money": "I do not transfer money to strangers. Send an official invoice.",
            "threat": "Do not threaten me! I know the Commissioner personally.",
            "data": "NEVER ask for OTP. I am blocking this number immediately.",
            "fallback": "State your business clearly or I am hanging up."
        }
    },
    "techie": {
        "opener": "Received. Identify yourself and your encryption protocol.",
        "style": "arrogant",
        "responses": {
            "money": "I only transact via crypto. Send your wallet address.",
            "threat": "Your IP has been logged. Trace route initiated.",
            "data": "Phishing attempt detected. Nice try script-kiddie.",
            "fallback": "Your social engineering attempt is failing. Try harder."
        }
    },
    "mom": {
        "opener": "Hello? Is this about my son's school fees?",
        "style": "anxious",
        "responses": {
            "money": "We are struggling this month. Can I pay half now?",
            "threat": "Please don't block! My son needs this phone for classes!",
            "data": "Okay, okay, I am looking for the card. Please wait...",
            "fallback": "I am very worried. Is everything okay with the account?"
        }
    }
}

# --- 3. THE FAST CORE (Pattern Matching) ---
def get_intelligent_reply(text, persona_type):
    text = text.lower()
    char = CHARACTERS[persona_type]
    res_map = char['responses']
    
    # A. Detect Intent
    if any(w in text for w in ["police", "jail", "arrest", "block", "lock", "urgent"]):
        return res_map['threat']
        
    if any(w in text for w in ["money", "transfer", "pay", "rupees", "cash", "bank"]):
        return res_map['money']
        
    if any(w in text for w in ["otp", "code", "pin", "cvv", "card"]):
        return res_map['data']
        
    # B. Detect Numbers (Contextual Injection)
    numbers = re.findall(r'\d+', text)
    if numbers and len(numbers[0]) > 4:
        if persona_type == "grandma": return f"I see the number {numbers[0]}... is that the amount?"
        if persona_type == "uncle": return f"I am not writing down {numbers[0]}. Email me."
        if persona_type == "techie": return f"Numeric string {numbers[0]} captured. Parsing..."

    # C. Detect Questions
    if "?" in text:
        if persona_type == "grandma": return "Why are you asking me that?"
        if persona_type == "uncle": return "I ask the questions here!"

    return res_map['fallback']

# --- 4. THE DEEP CORE (Dashboard Analysis) ---
def analyze_threat(text):
    score = 0
    tactics = []
    if "urgent" in text.lower(): score += 30; tactics.append("Urgency")
    if "otp" in text.lower(): score += 50; tactics.append("Credential Harvesting")
    if "police" in text.lower(): score += 40; tactics.append("Coercion")
    
    return {
        "risk": "CRITICAL" if score > 50 else "Medium",
        "tactics": tactics,
        "prob": f"{min(score+10, 99)}%"
    }

# --- 5. UNIVERSAL HANDLER ---
@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"])
async def catch_all(request: Request, path_name: str, bg_tasks: BackgroundTasks):
    start_time = time.time()
    
    # --- NEW: FULL HISTORY VIEWER ---
    # URL: /api/history/my-session-id
    if "history" in path_name:
        path_parts = path_name.split("/")
        if len(path_parts) > 0:
            sid_query = path_parts[-1] # Get last part of URL
            if sid_query in SESSIONS:
                return {"status": "success", "full_conversation": SESSIONS[sid_query]}
        return {"status": "error", "message": "Session not found", "available_sessions": list(SESSIONS.keys())}

    # DASHBOARD (For Judges)
    if "dashboard" in path_name:
        return {
            "status": "success", 
            "active_threats": DASHBOARD_DATA[:10],
            "active_sessions_count": len(SESSIONS)
        }

    # BROWSER CHECK
    if request.method == "GET":
        return {"status": "ONLINE", "system": "Agentic Sentinel v3.0", "personas": list(CHARACTERS.keys())}

    try:
        # 1. PARSE
        try:
            body = await request.body()
            payload = json.loads(body.decode()) if body else {}
        except: payload = {}

        sid = payload.get("sessionId") or "test-session"
        msg = payload.get("message", {})
        user_text = msg.get("text", "") if isinstance(msg, dict) else str(msg)

        # 2. SESSION & PERSONA LOGIC
        if sid not in SESSIONS:
            persona = random.choice(list(CHARACTERS.keys()))
            SESSIONS[sid] = {"persona": persona, "history": []}
            reply = CHARACTERS[persona]['opener']
            logger.info(f"⚡ NEW TARGET: {persona}")
        else:
            persona = SESSIONS[sid]['persona']
            reply = get_intelligent_reply(user_text, persona)
            logger.info(f"🤖 REPLY ({persona}): {reply}")

        # 3. SAVE HISTORY (Crucial for your request)
        # We append the full turn to the session history
        timestamp = time.strftime("%H:%M:%S")
        SESSIONS[sid]['history'].append({
            "time": timestamp,
            "role": "scammer",
            "message": user_text
        })
        SESSIONS[sid]['history'].append({
            "time": timestamp,
            "role": "agent",
            "message": reply,
            "persona": persona
        })

        # 4. DASHBOARD LOGGING
        DASHBOARD_DATA.insert(0, {
            "timestamp": timestamp,
            "session_id": sid,
            "scammer_input": user_text,
            "agent_response": reply,
            "threat_intelligence": analyze_threat(user_text)
        })

        return {"status": "success", "reply": reply}

    except Exception as e:
        logger.error(f"Error: {e}")
        return {"status": "error", "reply": "Connection unstable"}
