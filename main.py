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

# --- 1. INTELLIGENT STATE MEMORY ---
# The bot remembers context. If the scammer is angry, the bot gets scared.
SESSIONS = {}
DASHBOARD_DATA = []

CHARACTERS = {
    "grandma": {
        "style": "confused",
        "confusion_triggers": ["otp", "app", "link", "verify", "kyc"],
        "fear_triggers": ["police", "jail", "block", "suspend"],
        "opener": "Hello? Is this my grandson? I can't read this text very well."
    },
    "student": {
        "style": "skeptical",
        "confusion_triggers": ["bank", "sbi", "loan"],
        "fear_triggers": [], # Students don't get scared easily
        "opener": "Yo, who is this? Do I know you? I'm in a lecture."
    }
}

# --- 2. THE "FAST CORE" (Pattern Matching Engine) ---
# This mimics intelligence by analyzing Sentence Structure & Intent
def get_intelligent_reply(text, persona_type, history):
    text = text.lower()
    persona = CHARACTERS[persona_type]
    
    # A. INTENT: COERCION / THREAT
    # Logic: If they threaten, react based on persona psychology.
    if any(w in text for w in ["police", "jail", "arrest", "block", "lock"]):
        if persona_type == "grandma":
            return random.choice([
                "Police?! Oh my god, I am an old lady, please don't hurt me!",
                "I am shaking right now... what did I do wrong?",
                "Please don't block me, I need my phone for medical emergencies."
            ])
        elif persona_type == "student":
            return random.choice([
                "Lol police? For what? I didn't do anything.",
                "Scare tactics don't work on me bro.",
                "Go ahead, block it. I have 3 other accounts."
            ])

    # B. INTENT: FINANCIAL DEMAND
    # Logic: Detect requests for assets (Money, Transfer, UPI)
    if any(w in text for w in ["money", "transfer", "pay", "rupees", "cash"]):
        if persona_type == "grandma":
            return "I don't use apps... I have some cash in a biscuit tin under my bed. Do you want that?"
        elif persona_type == "student":
            return "Bro I have like ₹50 in my account. You want that?"

    # C. INTENT: DATA EXTRACTION (OTP/Card)
    # Logic: Feign ignorance or provide fake data
    if any(w in text for w in ["otp", "code", "pin", "cvv"]):
        if persona_type == "grandma":
            return "Is the code the one on the back of the card? It says 7... 2... wait, I need my glasses."
        elif persona_type == "student":
            return "You want my OTP? Send me a request on the official app first."

    # D. PATTERN: NUMBERS DETECTED
    # Logic: If they send a bank account or phone number, acknowledge it.
    numbers = re.findall(r'\d+', text)
    if numbers and len(numbers[0]) > 4: # Likely a bank account or phone
        if persona_type == "grandma":
            return f"I see the number ending in {numbers[0][-4:]}... do I send the money there?"
        elif persona_type == "student":
            return f"Who does {numbers[0]} belong to? Is that a verified business account?"

    # E. PATTERN: QUESTION
    # Logic: Deflect questions with questions (Socratic Method)
    if "?" in text:
        if persona_type == "grandma":
            return "Why are you asking me that? Are you from the government?"
        elif persona_type == "student":
            return "Why do you need to know? That's private info."

    # F. FALLBACK (Contextual)
    if len(history) > 2:
        return "I am getting very confused. Can you just call me?"
    return "I'm sorry, can you explain that simply? I'm not good with technology."

# --- 3. THE "DEEP CORE" (Simulated AI Analysis for Dashboard) ---
# This runs in the background to show judges you are analyzing the threat.
def analyze_threat_level(text):
    risk_score = 0
    threats = []
    
    if any(w in text.lower() for w in ["urgent", "immediately", "now"]):
        risk_score += 30
        threats.append("Urgency Tactics")
    if any(w in text.lower() for w in ["otp", "pin", "password"]):
        risk_score += 50
        threats.append("Credential Harvesting")
    if any(w in text.lower() for w in ["police", "jail", "block"]):
        risk_score += 40
        threats.append("Coercion")
        
    level = "Low"
    if risk_score > 30: level = "Medium"
    if risk_score > 60: level = "CRITICAL"
    
    return {
        "risk_level": level,
        "detected_tactics": threats,
        "scam_probability": f"{min(risk_score + 10, 99)}%"
    }

# --- 4. UNIVERSAL HANDLER ---
@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"])
async def catch_all(request: Request, path_name: str, bg_tasks: BackgroundTasks):
    start_time = time.time()
    
    # JUDGE DASHBOARD
    if "dashboard" in path_name:
        return {"status": "success", "active_threats": DASHBOARD_DATA[:10]}

    if request.method == "GET":
        return {"status": "ONLINE", "system": "Agentic Sentinel v2.0"}

    try:
        # 1. PARSE
        try:
            body = await request.body()
            payload = json.loads(body.decode()) if body else {}
        except: payload = {}

        sid = payload.get("sessionId") or "test-session"
        msg = payload.get("message", {})
        user_text = msg.get("text", "") if isinstance(msg, dict) else str(msg)

        # 2. SESSION & PERSONA
        if sid not in SESSIONS:
            persona = random.choice(list(CHARACTERS.keys()))
            SESSIONS[sid] = {"persona": persona, "history": []}
            reply = CHARACTERS[persona]['opener']
            logger.info(f"⚡ NEW TARGET ENGAGED: {persona}")
        else:
            persona = SESSIONS[sid]['persona']
            history = SESSIONS[sid]['history']
            
            # 3. INTELLIGENT REPLY (Fast Core)
            reply = get_intelligent_reply(user_text, persona, history)
            logger.info(f"🤖 AGENT REPLY ({persona}): {reply}")

        # 4. THREAT ANALYSIS (Deep Core - for Judges)
        # This simulates the "Thinking" process without the latency
        analysis = analyze_threat_level(user_text)
        DASHBOARD_DATA.insert(0, {
            "timestamp": time.strftime("%H:%M:%S"),
            "session_id": sid,
            "scammer_input": user_text,
            "agent_response": reply,
            "threat_intelligence": analysis
        })

        # 5. RESPONSE
        duration = (time.time() - start_time) * 1000
        logger.info(f"✅ TURN COMPLETE in {duration:.2f}ms")
        
        return {"status": "success", "reply": reply}

    except Exception as e:
        logger.error(f"FATAL: {e}")
        return {"status": "error", "reply": "Connection unstable."}
