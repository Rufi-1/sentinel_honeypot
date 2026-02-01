import os
import re
import random
import personas
from google import genai

# 1. READ KEY (Do not connect yet)
API_KEY = os.environ.get("GEMINI_API_KEY")

def get_client():
    """Connects to Google ONLY when needed."""
    if not API_KEY:
        print("❌ ERROR: GEMINI_API_KEY is missing.")
        return None
    try:
        return genai.Client(api_key=API_KEY)
    except Exception as e:
        print(f"❌ Client Init Error: {e}")
        return None

def detect_scam(text: str) -> bool:
    client = get_client()
    if not client: return True # Safety default
    
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash", 
            contents=f"Analyze intent: '{text}'. If scam/phishing/urgent money, reply SCAM. Else reply SAFE."
        )
        return "SCAM" in response.text.upper()
    except Exception as e:
        print(f"⚠️ Detect Error: {e}")
        return True 

def select_random_persona():
    # Safety fallback if personas.py is empty/broken
    try:
        return random.choice(list(personas.CHARACTERS.keys()))
    except:
        return "grandma"

def generate_reply(incoming_msg, history, persona_id):
    client = get_client()
    if not client: return "I am having connection issues."

    # Safety: Load persona or default to grandma
    char = personas.CHARACTERS.get(persona_id, personas.CHARACTERS.get('grandma', {}))
    
    chat_log = "\n".join([f"{m['sender']}: {m['text']}" for m in history])
    
    prompt = f"""
    SYSTEM: You are {char.get('name', 'Mrs. Higgins')}.
    TRAITS: {char.get('style', 'Confused')}
    TASK: Reply to the scammer. Keep it short.
    
    CHAT LOG:
    {chat_log}
    Scammer: {incoming_msg}
    Reply:
    """
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash", 
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"❌ Reply Error: {e}")
        return "I am confused. Can you say that again?"

def extract_intel(text):
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
