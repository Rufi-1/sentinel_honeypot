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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. CHARACTERS (With Anti-Loop Fallbacks) ---
CHARACTERS = {
    "grandma": {
        "opener": "Hello? Is this my grandson? I can't read this text very well.",
        "fallbacks": [
            "You keep repeating yourself dear. I am confused.",
            "I heard you, but I don't understand what you want.",
            "Can you just call my landline? This texting is too hard.",
            "Why are you saying the same thing over and over?"
        ]
    },
    "student": {
        "opener": "Yo, who is this? Do I know you? I'm in a lecture.",
        "fallbacks": [
            "Bro, stop spamming the same msg.",
            "You already said that. Are you a bot?",
            "Glitch in the matrix? Say something else.",
            "Boring. Send me the link or leave me alone."
        ]
    },
    "uncle": {
        "opener": "Who gave you this number? Speak fast, I am busy.",
        "fallbacks": [
            "Stop repeating yourself! I heard you the first time!",
            "Do not waste my time with copy-paste messages.",
            "State your business clearly or I am hanging up.",
            "Are you deaf? I asked you a question."
        ]
    }
}

# --- 2. SCENARIO DATABASE ---
# Key: Keywords to look for
# Value: [Grandma Reply, Student Reply, Uncle Reply]
SCENARIO_DB = {
    ("yes", "correct", "exactly", "right"): [
        "Okay, so what do you need me to do now?",
        "Cool. So what's the catch?",
        "Fine. Get to the point."
    ],
    ("money", "transfer", "cash", "rupees"): [
        "I have cash in the tin box. Do you want that?",
        "I'm broke bro. Ask my dad.",
        "I do not transfer money to strangers."
    ],
    ("bank", "sbi", "hdfc", "account"): [
        "Which bank? The one near the market?", 
        "I don't have a bank account lol.", 
        "I will visit the branch personally."
    ],
    ("otp", "code", "pin"): [
        "Is the code the numbers on the back of the card?", 
        "Nice try scammer.", 
        "NEVER ask for OTP. Reporting you."
    ],
    ("police", "jail", "block", "lock"): [
        "Police?! I didn't steal anything!", 
        "Lol police? For what?", 
        "I know the Commissioner. Back off."
    ],
    ("urgent", "immediate", "fast"): [
        "Why are you shouting? You are scaring me!", 
        "Chill, why the rush?", 
        "Do not pressure me."
    ]
}

SESSIONS = {}

# --- 3. INTELLIGENT REPLY GENERATION ---
def get_smart_reply(text, char_key, history):
    text_lower = text.lower()
    
    # A. Check Last Message (Loop Buster)
    # If the bot's last message is identical to what we plan to say, STOP.
    last_agent_msg = None
    if history and len(history) > 0:
        # Find the last message sent by 'agent'
        for m in reversed(history):
            if m['role'] == 'agent':
                last_agent_msg = m['content']
                break

    candidate_reply = None

    # B. Check Scenario DB
    # Shuffle keys so we don't always pick 'bank' first if multiple match
    keys = list(SCENARIO_DB.keys())
    random.shuffle(keys)
    
    for keywords in keys:
        if any(k in text_lower for k in keywords):
            responses = SCENARIO_DB[keywords]
            if char_key == "grandma": candidate_reply = responses[0]
            elif char_key == "student": candidate_reply = responses[1]
            elif char_key == "uncle": candidate_reply = responses[2]
            break
    
    # C. Heuristic Fallback (If no DB match)
    if not candidate_reply:
        if "?" in text:
            if char_key == "grandma": candidate_reply = "I am not sure... why do you ask?"
            elif char_key == "student": candidate_reply = "Why do you need to know?"
            elif char_key == "uncle": candidate_reply = "I ask the questions here."
        else:
            # Pick a random fallback from the character's list
            candidate_reply = random.choice(CHARACTERS[char_key]['fallbacks'])

    # D. THE FINAL LOOP CHECK
    # If the candidate reply is the SAME as what we just said, force a fallback
    if candidate_reply == last_agent_msg:
        logger.info(f"🔄 LOOP DETECTED! Switching to fallback for {char_key}")
        candidate_reply = random.choice(CHARACTERS[char_key]['fallbacks'])

    return candidate_reply

# --- 4. UNIVERSAL HANDLER ---
@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"])
async def catch_all(request: Request, path_name: str, bg_tasks: BackgroundTasks):
    start_time = time.time()
    
    if request.method == "GET":
        return {"status": "ONLINE", "mode": "LOOP_PROOF"}

    try:
        body_bytes = await request.body()
        try: payload = json.loads(body_bytes.decode())
        except: payload = {}

        sid = payload.get("sessionId") or "test-session"
        msg = payload.get("message", {})
        user_text = msg.get("text", "") if isinstance(msg, dict) else str(msg)

        # Initialize Session
        if sid not in SESSIONS:
            char_key = random.choice(list(CHARACTERS.keys()))
            SESSIONS[sid] = {"persona": char_key, "history": []}
            reply = CHARACTERS[char_key]['opener']
            logger.info(f"⚡ NEW SESSION: {char_key}")
        else:
            session = SESSIONS[sid]
            reply = get_smart_reply(user_text, session['persona'], session['history'])
            logger.info(f"🧠 REPLY: {reply}")

        # Update History
        SESSIONS[sid]['history'].append({"role": "scammer", "content": user_text})
        SESSIONS[sid]['history'].append({"role": "agent", "content": reply})

        duration = (time.time() - start_time) * 1000
        logger.info(f"✅ DONE in {duration:.2f}ms")
        
        return {"status": "success", "reply": reply}

    except Exception as e:
        logger.error(f"🔥 ERROR: {e}")
        return {"status": "error", "reply": "System Error"}
