from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import json
import logging
import database
import logic
import time

# 1. SETUP LOGGING
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI()

# 2. FIX THE INVISIBLE BLOCK (CORS) - CRITICAL STEP
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows ALL domains (including GUVI) to connect
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (POST, GET, OPTIONS)
    allow_headers=["*"],  # Allows all headers (x-api-key, etc.)
)

# 3. GLOBAL TRAFFIC LOGGER (See every knock at the door)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    # Log that a request is trying to enter
    logger.info(f"🔔 KNOCK KNOCK: {request.method} {request.url}")
    
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        logger.info(f"✅ SENT RESPONSE: {response.status_code} (took {process_time:.2f}ms)")
        return response
    except Exception as e:
        logger.error(f"🔥 SERVER CRASHED DURING REQUEST: {e}")
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

# 4. THE UNIVERSAL ENDPOINT
@app.post("/api/chat")
async def chat_endpoint(request: Request):
    try:
        # A. READ RAW DATA
        body_bytes = await request.body()
        body_str = body_bytes.decode()
        logger.info(f"📥 BODY RECEIVED: {body_str}")

        # B. PARSE JSON
        try:
            payload = json.loads(body_str)
        except:
            payload = {}

        # C. EXTRACT DATA (Safe Mode)
        # Handle "sessionId" OR "session_id"
        session_id = payload.get("sessionId") or payload.get("session_id") or "fallback-session"
        
        # Handle message format
        msg_data = payload.get("message", {})
        if isinstance(msg_data, dict):
            user_text = msg_data.get("text", "Hello")
        else:
            user_text = str(msg_data)

        # D. CORE LOGIC
        # Get/Create Session
        session = database.get_session(session_id)
        if not session:
            try:
                # Try to get a persona, fallback to grandma if random fails
                persona = logic.select_random_persona()
            except:
                persona = "grandma"
            database.create_session(session_id, persona)
            session = {"persona_id": persona, "is_scam": False}

        # Generate Reply
        try:
            history = database.get_history(session_id)
            # Ensure we send a string persona_id, not a dict/object
            current_persona = str(session.get('persona_id', 'grandma'))
            reply = logic.generate_reply(user_text, history, current_persona)
        except Exception as logic_err:
            logger.error(f"⚠️ Logic Error: {logic_err}")
            reply = "I am having trouble connecting. Can you repeat that?"

        # Save to DB (Fire and Forget)
        try:
            database.save_message(session_id, "scammer", user_text)
            database.save_message(session_id, "agent", reply)
            
            # Simple Intel Extraction
            intel = logic.extract_intel(user_text + " " + reply)
            database.update_intel(session_id, intel)
        except Exception as db_err:
            logger.error(f"⚠️ DB Error: {db_err}")

        # E. RETURN SUCCESS
        response_data = {
            "status": "success",
            "reply": reply
        }
        logger.info(f"📤 REPLYING WITH: {response_data}")
        return response_data

    except Exception as e:
        logger.error(f"🔥 CRITICAL HANDLER ERROR: {e}")
        return {
            "status": "error",
            "reply": "System Error"
        }

@app.get("/")
def home():
    return {"status": "ONLINE", "mode": "CORS-ENABLED"}

if __name__ == "__main__":
    import uvicorn
    # Important: Bind to 0.0.0.0 so Render can see it
    uvicorn.run(app, host="0.0.0.0", port=8000)
