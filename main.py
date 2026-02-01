from fastapi import FastAPI, Header, HTTPException, BackgroundTasks, Request
from typing import Optional, Dict, Any
import logging
import database
import logic

# 1. SETUP LOGGING (So we can see exactly what GUVI sends in the Render logs)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI(title="Sentinel Polymorphic Node")

# --- BACKGROUND WORKER ---
def background_tasks_handler(session_id, user_text, agent_text):
    try:
        # Robust check to ensure IDs are strings
        sid = str(session_id)
        
        database.save_message(sid, "scammer", user_text)
        database.save_message(sid, "agent", agent_text)
        
        combined_text = f"{user_text} {agent_text}"
        intel = logic.extract_intel(combined_text)
        final_intel = database.update_intel(sid, intel)
        
        history = database.get_history(sid)
        
        # Report logic
        if final_intel.get('phishingLinks') or final_intel.get('upiIds') or len(history) > 4:
            import requests
            requests.post(
                "https://hackathon.guvi.in/api/updateHoneyPotFinalResult",
                json={
                    "sessionId": sid,
                    "scamDetected": True,
                    "totalMessagesExchanged": len(history),
                    "extractedIntelligence": final_intel,
                    "agentNotes": "Sentinel Active"
                },
                timeout=1
            )
            logger.info(f"✅ REPORTED {sid}")
    except Exception as e:
        logger.error(f"⚠️ Background Error: {e}")

# --- THE UNIVERSAL ENDPOINT ---
@app.post("/api/chat")
async def chat_endpoint(request: Request, bg_tasks: BackgroundTasks, x_api_key: Optional[str] = Header(None)):
    
    # 1. READ RAW DATA (Bypass strict validation)
    try:
        payload = await request.json()
        logger.info(f"📥 RECEIVED PAYLOAD: {payload}") # <--- LOOK AT THIS IN LOGS IF IT FAILS
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # 2. MANUAL EXTRACTION (Flexible Logic)
    # We check for 'sessionId' OR 'session_id' to be safe
    session_id = payload.get("sessionId") or payload.get("session_id")
    if not session_id:
        # Generate a random one if missing (Emergency Fallback)
        import uuid
        session_id = str(uuid.uuid4())
        logger.warning("⚠️ Missing sessionId, generated temporary one.")

    # Handle Message Structure
    # Expecting: "message": {"text": "..."}
    message_data = payload.get("message", {})
    if isinstance(message_data, str):
        msg_text = message_data # If they sent just a string
    else:
        msg_text = message_data.get("text") or message_data.get("content") or "Hello"

    # 3. SECURITY CHECK
    # We allow the key to be missing for local tests, but check if present
    if x_api_key and x_api_key != "my-secret-key":
        logger.warning(f"⚠️ Wrong Key: {x_api_key}")
        raise HTTPException(status_code=401, detail="Invalid X-API-KEY")

    # 4. CORE LOGIC
    # Get/Create Session
    session = database.get_session(session_id)
    if not session:
        persona = logic.select_random_persona()
        database.create_session(session_id, persona)
        session = {"persona_id": persona, "is_scam": False}

    # Detect Scam
    if not session['is_scam']:
        if logic.detect_scam(msg_text):
            pass 
        else:
            return {"status": "success", "reply": "I am not interested."}

    # Generate Reply
    history = database.get_history(session_id)
    pid = session.get('persona_id', 'grandma')
    reply = logic.generate_reply(msg_text, history, pid)

    # Queue Background Task
    bg_tasks.add_task(background_tasks_handler, session_id, msg_text, reply)

    return {"status": "success", "reply": reply}

@app.get("/")
def home():
    return {"status": "ONLINE", "message": "Universal Sentinel Active"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
