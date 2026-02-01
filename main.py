from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import json
import logging
import database
import logic

# Setup Logs so we can see the "Real" error in Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI()

@app.post("/api/chat")
async def chat_endpoint(request: Request):
    try:
        # 1. GET RAW BODY (No Validation)
        # We read the raw text bytes to see EXACTLY what they sent
        body_bytes = await request.body()
        body_str = body_bytes.decode()
        logger.info(f"📥 RAW INCOMING DATA: {body_str}")

        # 2. TRY TO PARSE JSON
        try:
            payload = json.loads(body_str)
        except:
            # If they sent garbage, just assume it's a test ping
            logger.warning("⚠️ Could not parse JSON. Using empty dict.")
            payload = {}

        # 3. EXTRACT DATA SAFELY (No Crashes)
        # Handle case where sessionId is missing
        session_id = payload.get("sessionId") or payload.get("session_id") or "fallback-session-001"
        
        # Handle case where message is missing or structured differently
        msg_data = payload.get("message", {})
        if isinstance(msg_data, dict):
            user_text = msg_data.get("text", "Hello")
        else:
            user_text = str(msg_data)

        # 4. LOGIC (Wrapped in try/except to prevent 500 Errors)
        try:
            # Check/Create Session
            session = database.get_session(session_id)
            if not session:
                # Fallback to 'grandma' if random fails
                database.create_session(session_id, "grandma")
                session = {"persona_id": "grandma", "is_scam": False}

            # Generate Reply
            history = database.get_history(session_id)
            reply = logic.generate_reply(user_text, history, session.get('persona_id', 'grandma'))
            
            # (Optional) Run background task logic here if needed
            # For debugging, we just want to reply successfully first
            
        except Exception as logic_error:
            logger.error(f"⚠️ Logic Error: {logic_error}")
            reply = "I am confused. Can you explain?"

        # 5. RETURN SUCCESS (Always return 200 OK)
        return {
            "status": "success",
            "reply": reply
        }

    except Exception as e:
        # GLOBAL CATCH-ALL: If anything explodes, still return JSON
        logger.error(f"🔥 CRITICAL ERROR: {e}")
        return {
            "status": "error",
            "reply": "System Error - Check Logs"
        }

@app.get("/")
def home():
    return {"status": "Online"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
