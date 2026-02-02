from fastapi import FastAPI, Request, BackgroundTasks
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. THE CHARACTERS ---
CHARACTERS = {
    "grandma": {
        "name": "Mrs. Higgins",
        "opener": "Hello? Is this my grandson? I can't read this text very well.",
        "style": "confused"
    },
    "student": {
        "name": "Rohan",
        "opener": "Yo, who is this? Do I know you? I'm in a lecture.",
        "style": "skeptical"
    },
    "uncle": {
        "name": "Uncle Raj",
        "opener": "Who gave you this number? Speak fast, I am busy.",
        "style": "aggressive"
    }
}

# --- 2. THE KNOWLEDGE BASE (Common Scams) ---
# Maps keywords to character-specific responses
SCENARIO_DB = {
    # [Keywords] -> [Grandma, Student, Uncle]
    ("money", "transfer", "cash", "rupees", "paid"): [
        "I have some cash in the biscuit tin. Do you want that?",
        "Bro, I'm broke. Ask my dad if you want money.",
        "I do not transfer money to strangers. Who are you?"
    ],
    ("bank", "sbi", "hdfc", "icici", "account"): [
        "Which bank? The one near the vegetable market?",
        "I don't even have a bank account yet, lol.",
        "I will visit the branch manager personally. Don't call me."
    ],
    ("otp", "code", "pin", "password"): [
        "Is the code the numbers on the back of the card?",
        "You want my OTP? Nice try scammer.",
        "NEVER ask for OTP. I am reporting this number."
    ],
    ("police", "jail", "arrest", "cbi"): [
        "Police?! Oh my god, I didn't steal the extra sugar packet!",
        "Lol police? For what? Downloading movies?",
        "I know the Commissioner. Do not threaten me."
    ],
    ("lottery", "winner", "prize", "gift"): [
        "A prize? Did I win the bingo at the community center?",
        "Fake news. Stop spamming me.",
        "I did not enter any lottery. Stop lying."
    ],
    ("click", "link", "website", "app", "download"): [
        "I touched the blue text but nothing happened.",
        "I'm not clicking that suspicious link, bro.",
        "I do not download random apps on my business phone."
    ]
}

# --- 3. THE HEURISTIC ENGINE (Handles "Unknowns") ---
def get_heuristic_reply(text, char_key):
    """Generates a smart reply based on sentence structure when no keywords match."""
    
    # Analyze the input
    is_question = "?" in text
    is_shouting = text.isupper() or "!" in text
    has_number = bool(re.search(r'\d+', text))
    is_short = len(text.split()) < 3
    
    # 1. Handle Aggression/Urgency
    if is_shouting:
        if char_key == "grandma": return "Why are you shouting? You are scaring me!"
        if char_key == "student": return "Woah, chill out. Why the caps?"
        if char_key == "uncle":   return "Do not raise your voice at me!"

    # 2. Handle Numbers (Likely amounts or codes)
    if has_number:
        if char_key == "grandma": return "I see some numbers... is that the amount I have to pay?"
        if char_key == "student": return "What are those numbers? Is that a code?"
        if char_key == "uncle":   return "I am not writing down those numbers. Send an email."

    # 3. Handle Questions
    if is_question:
        if char_key == "grandma": return "I... I am not sure. Why do you ask?"
        if char_key == "student": return "Why do you need to know that?"
        if char_key == "uncle":   return "I ask the questions here. Who are you?"

    # 4. Handle Short/Confusing messages
    if is_short:
        if char_key == "grandma": return "Hello? Are you still there?"
        if char_key == "student": return "???"
        if char_key == "uncle":   return "Speak clearly."

    # 5. Ultimate Fallback (Polymorphic)
    if char_key == "grandma": return "I am sorry, my hearing aid is whistling. Can you explain that again?"
    if char_key == "student": return "Bro, I have no idea what you're talking about."
    if char_key == "uncle":   return "This is a waste of my time. State your business or I hang up."

# --- 4. SESSION STORAGE ---
SESSIONS = {}

# --- 5. THE HANDLER ---
async def handle_chat(request: Request, bg_tasks: BackgroundTasks):
    start_time = time.time()
    try:
        body = await request.body()
        try: payload = json.loads(body.decode())
        except: payload = {}

        sid = payload.get("sessionId") or "test-session"
        msg = payload.get("message", {})
        user_text = msg.get("text", "") if isinstance(msg, dict) else str(msg)
        user_lower = user_text.lower()

        # A. Initialize Session
        if sid not in SESSIONS:
            char_key = random.choice(list(CHARACTERS.keys()))
            SESSIONS[sid] = {"persona": char_key, "history": []}
            reply = CHARACTERS[char_key]['opener']
            logger.info(f"⚡ NEW SESSION: {char_key}")
        
        else:
            # B. Generate Reply
            char_key = SESSIONS[sid]['persona']
            reply = None
            
            # Step 1: Check Knowledge Base (Exact Match)
            for keywords, responses in SCENARIO_DB.items():
                if any(k in user_lower for k in keywords):
                    # Index 0=Grandma, 1=Student, 2=Uncle
                    if char_key == "grandma": reply = responses[0]
                    elif char_key == "student": reply = responses[1]
                    elif char_key == "uncle": reply = responses[2]
                    logger.info(f"🧠 KNOWLEDGE BASE HIT: {keywords[0]}")
                    break
            
            # Step 2: Heuristic Engine (Smart Fallback)
            if not reply:
                reply = get_heuristic_reply(user_text, char_key)
                logger.info(f"🧩 HEURISTIC ENGINE USED ({char_key})")

        # C. Update History
        SESSIONS[sid]['history'].append({"role": "scammer", "content": user_text})
        SESSIONS[sid]['history'].append({"role": "agent", "content": reply})

        # D. Mock Intel Extraction (Background)
        # (This is where you'd normally put the slow AI logic)
        
        duration = (time.time() - start_time) * 1000
        logger.info(f"✅ REPLY TIME: {duration:.2f}ms")
        
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
def home(): return {"status": "ONLINE", "mode": "HEURISTIC_EXPERT_SYSTEM"}
