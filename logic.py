# logic.py
import os
import re
import random
import personas
from google import genai
from google.genai import types

# --- CONFIG ---
# Hardcode key for easier deployment or use os.environ
# logic.py

# ... imports ...
import os # Make sure this is imported at the top

# OLD WAY (BAD - Delete this line):
# API_KEY = "AIzaSy......" 

# NEW WAY (GOOD - Safe):
API_KEY = os.environ.get("GEMINI_API_KEY") 

client = genai.Client(api_key=API_KEY)

def detect_scam(text: str) -> bool:
    """Fast check: Is this a scam?"""
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"Analyze intent: '{text}'. If scam/phishing/urgent money, reply SCAM. Else reply SAFE."
        )
        return "SCAM" in response.text.upper()
    except:
        return True # Default to caution

def select_random_persona():
    """Polymorphic Selector"""
    return random.choice(list(personas.CHARACTERS.keys()))

def generate_reply(incoming_msg, history, persona_id):
    """Becomes the specific character."""
    char = personas.CHARACTERS.get(persona_id, personas.CHARACTERS['grandma'])
    chat_log = "\n".join([f"{m['sender']}: {m['text']}" for m in history])
    
    prompt = f"""
    SYSTEM: You are {char['name']}, a {char['role']}.
    TRAITS: {char['style']}
    STRATEGY: {char['strategy']}
    TASK: Reply to the scammer. Keep it short (1-2 sentences). Do NOT expose yourself.
    
    CHAT LOG:
    {chat_log}
    Scammer: {incoming_msg}
    {char['name']}:
    """
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        return response.text.strip()
    except:
        return "I am confused. Can you say that again?"

def extract_intel(text):
    """Hybrid: Regex + AI for tricky data."""
    # 1. Regex Pass (Fast)
    data = {
        "upiIds": re.findall(r"[\w\.-]+@[\w\.-]+", text),
        "phishingLinks": re.findall(r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+", text),
        "phoneNumbers": re.findall(r"(?:\+91|0)?[6-9]\d{9}", text),
        "bankAccounts": re.findall(r"\b\d{9,18}\b", text),
        "suspiciousKeywords": []
    }
    
    # 2. AI Clean-up Pass (Smart) - runs if numbers found
    if any(char.isdigit() for char in text):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"Extract ONLY bank account numbers and UPI IDs from this text: '{text}'. Return JSON."
            )
            # (Simplified: In production, parse this JSON to augment regex results)
        except:
            pass
            

    return data
