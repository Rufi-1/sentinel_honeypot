import os
import re
import random
import personas
from google import genai

# --- CONFIGURATION ---
# Try to get key from Environment, otherwise print warning
API_KEY = os.environ.get("GEMINI_API_KEY")

# --- HELPER: CONNECT TO GOOGLE ---
def get_client():
    if not API_KEY:
        print("❌ ERROR: API Key is missing.")
        return None
    try:
        return genai.Client(api_key=API_KEY)
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return None

# --- 1. DETECT SCAM ---
def detect_scam(text: str) -> bool:
    client = get_client()
    if not client: return True # Default to scam if API fails
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Analyze intent: '{text}'. If scam/phishing/urgent money, reply SCAM. Else reply SAFE."
        )
        return "SCAM" in response.text.upper()
    except:
        return True

# --- 2. SELECT PERSONA ---
def select_random_persona():
    try:
        return random.choice(list(personas.CHARACTERS.keys()))
    except:
        return "grandma"

# --- 3. GENERATE REPLY (THE MISSING FUNCTION) ---
def generate_reply(incoming_msg, history, persona_id):
    """
    This is the function that was missing! 
    It generates the actual response text.
    """
    client = get_client()
    
    # 1. Fallback if API fails
    if not client: 
        return "I am having connection issues. Can you repeat that?"

    # 2. Get Character Data
    char = personas.CHARACTERS.get(persona_id, personas.CHARACTERS.get('grandma', {}))
    
    # 3. Format History
    chat_log = "\n".join([f"{m['sender']}: {m['text']}" for m in history])
    
    # 4. Prompt Gemini
    prompt = f"""
    SYSTEM: You are {char.get('name', 'Mrs. Higgins')}.
    TRAITS: {char.get('style', 'Confused')}
    STRATEGY: {char.get('strategy', 'Waste time')}
    TASK: Reply to the scammer. Keep it short (1 sentence). Do NOT expose that you are an AI.
    
    CHAT LOG:
    {chat_log}
    Scammer: {incoming_msg}
    Reply:
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"❌ AI Gen Error: {e}")
        return "I am confused. Can you say that again?"

# --- 4. EXTRACT INTEL ---
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
