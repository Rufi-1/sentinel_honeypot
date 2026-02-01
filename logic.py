import os
import re
import random
import personas
from google import genai

# 1. SECURE KEY EXTRACTION
# We use os.environ.get to safely read the key from Render
API_KEY = os.environ.get("GEMINI_API_KEY")

# Safety Check: If key is missing, print it to logs (masked)
if not API_KEY:
    print("❌ CRITICAL: GEMINI_API_KEY is missing in Environment Variables!")
else:
    print(f"✅ API Key Loaded (starts with {API_KEY[:4]}...)")

client = genai.Client(api_key=API_KEY)

def detect_scam(text: str) -> bool:
    try:
        # Switch to 2.5-flash (More stable)
        response = client.models.generate_content(
            model="gemini-1.5-flash", 
            contents=f"Analyze intent: '{text}'. If scam/phishing/urgent money, reply SCAM. Else reply SAFE."
        )
        return "SCAM" in response.text.upper()
    except Exception as e:
        print(f"⚠️ Detect Scam Error: {e}")
        return True 

def select_random_persona():
    return random.choice(list(personas.CHARACTERS.keys()))

def generate_reply(incoming_msg, history, persona_id):
    char = personas.CHARACTERS.get(persona_id, personas.CHARACTERS['grandma'])
    chat_log = "\n".join([f"{m['sender']}: {m['text']}" for m in history])
    
    prompt = f"""
    SYSTEM: You are {char['name']}, a {char['role']}.
    TRAITS: {char['style']}
    STRATEGY: {char['strategy']}
    TASK: Reply to the scammer. Keep it short. Do NOT expose yourself.
    
    CHAT LOG:
    {chat_log}
    Scammer: {incoming_msg}
    {char['name']}:
    """
    try:
        # Switch to 2.5-flash
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"❌ AI Reply Error: {e}")
        return "Oh dear, my internet is slow. Can you explain that simply?"

def extract_intel(text):
    # Regex + Basic keyword checks
    data = {
        "upiIds": re.findall(r"[\w\.-]+@[\w\.-]+", text),
        "phishingLinks": re.findall(r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+", text),
        "phoneNumbers": re.findall(r"(?:\+91|0)?[6-9]\d{9}", text),
        "bankAccounts": re.findall(r"\b\d{9,18}\b", text),
        "suspiciousKeywords": []
    }
    if "blocked" in text.lower() or "urgent" in text.lower():
        data["suspiciousKeywords"].append("Urgency")
    return data
