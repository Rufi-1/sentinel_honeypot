import os
import re
import random
import personas
from google import genai

# 1. SECURELY LOAD KEY
# We look for the variable. If not found, it defaults to None.
RAW_KEY = os.environ.get("GEMINI_API_KEY")

# 2. DEBUGGING BLOCK (Crucial)
# This prints to Render Logs so you can see if it worked, but hides the secret.
if not RAW_KEY:
    print("🔒 SECURITY LOG: GEMINI_API_KEY is MISSING or NONE.")
    API_KEY = None
else:
    # Print only the first 4 chars to prove it loaded (e.g., "AIza...")
    masked = f"{RAW_KEY[:4]}...{RAW_KEY[-4:]}"
    print(f"🔒 SECURITY LOG: API Key Loaded Successfully! ({masked})")
    # Clean the key just in case there are spaces (The Silent Killer)
    API_KEY = RAW_KEY.strip()

def get_client():
    if not API_KEY:
        print("❌ ERROR: Cannot connect. API Key is missing.")
        return None
    try:
        return genai.Client(api_key=API_KEY)
    except Exception as e:
        print(f"❌ Client Init Error: {e}")
        return None

# ... (Rest of your functions: detect_scam, select_random_persona, etc. remain the same) ...
