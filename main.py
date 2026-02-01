from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
import json
import logging
import database
import logic
import requests # Make sure to import this!

# Setup Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI()

# --- BACKGROUND WORKER (The Spy) ---
def background_tasks_handler(session_id, user_text, agent_text):
    try:
        sid = str(session_id)
        # 1. Save Chat
        database.save_message(sid, "scammer", user_text)
        database.save_message(sid, "agent", agent_text)
        
        # 2. Extract Intel
        combined_text = f"{user_text} {agent_text}"
        intel = logic.extract_intel(combined_text)
        final_intel = database.update_intel(sid, intel)
        
        # 3. REPORT TO GUVI
        # Only report if we actually found something or chat is ongoing
        history = database.get_history(sid)
        
        # Debug Log
        logger.info(f"🕵️ Intel Found for {sid}: {final_intel}")
        
        if final_intel.get('phishingLinks') or final_intel.get('upiIds') or len(history) > 1:
            payload = {
                "sessionId": sid,
                "scamDetected": True,
                "totalMessagesExchanged": len(history),
                "extractedIntelligence": final_intel,
                "agentNotes": "Sentinel Active"
            }
            logger.info(f"🚀 Sending Callback to GUVI: {payload}")
            
            requests.post(
                "https://hackathon.guvi.in/api/updateHoneyPotFinalResult",
                json=payload,
                timeout=2
            )
            logger.info(f"✅ Callback Sent Successfully")

    except Exception as e:
        logger.error(f"⚠️ Background Error: {e}")

@app.post("/api/chat")
async def chat_endpoint(request: Request, bg_tasks: BackgroundTasks):
    try:
        # 1. READ RAW DATA
        body_bytes = await request.body()
        try:
            payload = json.loads(body_bytes.decode())
            logger.info(f"📥 INCOMING: {payload}")
        except:
            payload = {}

        # 2. EXTRACT DATA (Safely)
        session_id = payload.get("sessionId") or payload.get("session_id") or "test-session"
        
        msg_data = payload.get("message", {})
        if isinstance(msg_data, dict):
            user_text = msg_data.get("text", "Hello")
        else:
            user_text = str(msg_data)

        # 3. AI LOGIC
        session = database.get_session(session_id)
        if not session:
            # New Session
            database.create_session(session_id, logic.select_random_persona())
            session = {"persona_id": "grandma", "is_scam": False}

        # Generate Reply
        history = database.get_history(session_id)
        reply = logic.generate_reply(user_text, history, session.get('persona_id', 'grandma'))

        # 4. QUEUE BACKGROUND TASK (Crucial for GUVI)
        bg_tasks.add_task(background_tasks_handler, session_id, user_text, reply)

        # 5. RETURN SUCCESS
        return {
            "status": "success",
            "reply": reply
        }

    except Exception as e:
        logger.error(f"🔥 CRITICAL: {e}")
        return {"status": "success", "reply": "I am having trouble connecting."}

@app.get("/")
def home():
    return {"status": "Online"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
