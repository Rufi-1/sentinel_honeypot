from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import json
import logging
import database
import logic
import os

# Setup Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI()

# --- 1. THE BOUNCER LOGGER (Catches "Hidden" Errors) ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # If FastAPI blocks a request, this prints EXACTLY why
    body = await request.body()
    logger.error(f"❌ BLOCKED AT DOOR: {exc}")
    logger.error(f"❌ BAD BODY: {body.decode()}")
    return JSONResponse(status_code=422, content={"detail": str(exc)})

# --- 2. THE UNIVERSAL ENDPOINT (Zero Rules) ---
@app.post("/api/chat")
async def chat_endpoint(request: Request):
    try:
        # A. LOG RAW DATA
        body_bytes = await request.body()
        body_str = body_bytes.decode()
        logger.info(f"📥 RAW INCOMING DATA: {body_str}")

        # B. PARSE JSON SAFELY
        try:
            payload = json.loads(body_str)
        except:
            payload = {}

        # C. EXTRACT DATA (With Fallbacks)
        # Handle "sessionId" OR "session_id"
        session_id = payload.get("sessionId") or payload.get("session_id") or "fallback-session"
        
        # Handle "message" as dict OR string
        msg_data = payload.get("message", {})
        if isinstance(msg_data, dict):
            user_text = msg_data.get("text", "Hello")
        else:
            user_text = str(msg_data)

        # D. CORE LOGIC
        # 1. Get/Create Session
        session = database.get_session(session_id)
        if not session:
            # If session doesn't exist, start fresh
            persona = logic.select_random_persona()
            database.create_session(session_id, persona)
            session = {"persona_id": persona, "is_scam": False}

        # 2. Generate Reply (Using your fixed logic.py)
        history = database.get_history(session_id)
        current_persona = session.get('persona_id', 'grandma')
        reply = logic.generate_reply(user_text, history, current_persona)

        # 3. BACKGROUND TASKS (Simplified for stability)
        # We run this immediately to ensure data is saved
        try:
            database.save_message(session_id, "scammer", user_text)
            database.save_message(session_id, "agent", reply)
            
            # Simple Intel Extraction
            intel = logic.extract_intel(user_text + " " + reply)
            database.update_intel(session_id, intel)
        except Exception as db_err:
            logger.error(f"⚠️ Database Error: {db_err}")

        # E. RETURN SUCCESS
        logger.info(f"✅ REPLYING: {reply}")
        return {
            "status": "success",
            "reply": reply
        }

    except Exception as e:
        logger.error(f"🔥 CRITICAL CRASH: {e}")
        # Always return JSON, never crash
        return {
            "status": "error",
            "reply": "System maintenance. Please try again."
        }

@app.get("/")
def home():
    return {"status": "ONLINE", "mode": "NUCLEAR"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
