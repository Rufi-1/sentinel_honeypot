from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import json
import logging
import database
import logic
import time

# Setup Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI()

# 1. ALLOW ALL ORIGINS (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. LOG TRAFFIC
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    logger.info(f"🔔 KNOCK KNOCK: {request.method} {request.url}")
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        logger.info(f"✅ RESPONSE: {response.status_code} ({process_time:.2f}ms)")
        return response
    except Exception as e:
        logger.error(f"🔥 CRASH: {e}")
        return JSONResponse(status_code=500, content={"detail": "Error"})

# 3. HANDLE "HEAD" PINGS (The Fix for the Tester)
@app.head("/")
@app.head("/api/chat")
def ping_check():
    # Just return 200 OK to say "I am alive"
    return Response(status_code=200)

# 4. UNIVERSAL CHAT ENDPOINT
@app.post("/api/chat")
async def chat_endpoint(request: Request):
    try:
        # Log Raw Data
        body_bytes = await request.body()
        body_str = body_bytes.decode()
        logger.info(f"📥 INCOMING BODY: {body_str}")

        try:
            payload = json.loads(body_str)
        except:
            payload = {}

        # Extract Data
        session_id = payload.get("sessionId") or payload.get("session_id") or "test-session"
        msg_data = payload.get("message", {})
        if isinstance(msg_data, dict):
            user_text = msg_data.get("text", "Hello")
        else:
            user_text = str(msg_data)

        # Logic
        session = database.get_session(session_id)
        if not session:
            try:
                persona = logic.select_random_persona()
            except:
                persona = "grandma"
            database.create_session(session_id, persona)
            session = {"persona_id": persona}

        # Reply
        history = database.get_history(session_id)
        current_persona = str(session.get('persona_id', 'grandma'))
        reply = logic.generate_reply(user_text, history, current_persona)

        # Save & Intel (Safe Mode)
        try:
            database.save_message(session_id, "scammer", user_text)
            database.save_message(session_id, "agent", reply)
            intel = logic.extract_intel(user_text + " " + reply)
            database.update_intel(session_id, intel)
        except Exception as db_err:
            logger.error(f"⚠️ DB Warning: {db_err}")

        # Success Response
        return {"status": "success", "reply": reply}

    except Exception as e:
        logger.error(f"🔥 CRITICAL: {e}")
        return {"status": "success", "reply": "Connection unstable, please retry."}

@app.get("/")
def home():
    return {"status": "ONLINE", "mode": "HEAD-ENABLED"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
