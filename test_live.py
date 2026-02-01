import requests
import json

# 1. THE TARGET (Your Live Cloud URL)
API_URL = "https://sentinel-honeypot-api.onrender.com/api/chat"

# 2. THE KEY (Must match what you set in Render Environment Variables)
API_KEY = "my-secret-key"

# 3. THE "ATTACK" DATA
payload = {
    "sessionId": "live-test-001",
    "message": {
        "sender": "scammer",
        "text": "Your account is blocked. Click here immediately: http://bit.ly/scam-link",
        "timestamp": "2026-02-01T12:00:00Z"
    },
    "conversationHistory": []
}

headers = {
    "x-api-key": API_KEY,
    "Content-Type": "application/json"
}

print(f"🚀 Sending scam message to: {API_URL}...")

try:
    response = requests.post(API_URL, json=payload, headers=headers)
    
    # CHECK THE RESULT
    if response.status_code == 200:
        print("\n✅ SUCCESS! The Sentinel replied:")
        data = response.json()
        print(f"🤖 Agent Reply: {data['reply']}")
    else:
        print(f"\n❌ ERROR (Status {response.status_code}):")
        print(response.text)

except Exception as e:
    print(f"\n⚠️ CONNECTION FAILED: {e}")