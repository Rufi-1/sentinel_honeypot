from fastapi import FastAPI, Header, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from typing import List, Optional, Any
import requests
import database
import logic
import json

app = FastAPI(title="Sentinel Polymorphic Node")

# --- 1. DEFENSIVE DATA MODELS (The Fix) ---
# We use 'Optional' and defaults (= None) to prevent crashes if fields are missing

class Msg(BaseModel):
    sender: str
    text: str
    # Make timestamp optional just in case the tester skips it
    timestamp: Optional[str] = None 

class Payload(BaseModel):
    sessionId: str
    message: Msg
    # Default to empty list if missing
    conversationHistory: List[Msg] = []
    # Default to empty dict if missing
    metadata: Optional[dict] = {}

# --- 2. DEBUGGING HANDLER (Crucial) ---
# This will print the EXACT error to your Render Logs so we know what's wrong
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    error_details = exc.errors()
    print(f"❌ VALIDATION ERROR: {error_details}") # Check Render Logs for this!
    body = await request.body()
    print(f"❌ RECEIVED BODY: {body.decode()}")
    return JSONResponse(
        status_code=422,
        content={"detail": error_details, "body": body.decode()},
    )

# --- 3. BACKGROUND WORKER ---
def background_tasks_handler(session_id, user_text, agent_text):
    # Safe checks to prevent crashing if logic fails
    try:
        database.save_message(session_id, "scammer", user_text)
        database.save_message(session_id, "agent", agent_text)
        
        combined_text = f"{user_text} {agent_text}"
        intel = logic.extract_intel(combined_text)
        final_intel = database.update_intel(session_id, intel)
        
        history = database.get_history(session_id)
        
        # Only report if we have valid intel
        if final_intel.get('phishingLinks') or final_intel.get('upiIds') or len(history) > 4:
            requests.post(
                "https://hackathon.guvi.in/api/updateHoneyPotFinalResult",
                json={
                    "sessionId": session_id,
                    "scamDetected": True,
                    "totalMessagesExchanged": len(history),
                    "extractedIntelligence": final_intel,
                    "agentNotes": "Sentinel Node Active"
                },
                timeout=1
            )
            print(f"✅ REPORTED {session_id}")
    except Exception as e:
        print(f"⚠️ Background Task Error: {e}")

# --- 4. API ENDPOINT ---
@app.post("/api/chat")
async def chat_endpoint(payload: Payload, bg_tasks: BackgroundTasks, x_api_key: Optional[str] = Header(None)):
    
    # 1. Security Check (Allow None for local testing if needed, but strict for prod)
    if x_api_key != "my-secret-key":
        # Some testers send the key in weird ways, print it to debug
        print(f"⚠️ Auth Failed. Received Key: {x_api_key}")
        raise HTTPException(status_code=401, detail="Invalid or Missing X-API-KEY")
    
    sid = payload.sessionId
    msg_text = payload.message.text
    
    # 2. Session Management
    session = database.get_session(sid)
    if not session:
        persona = logic.select_random_persona()
        database.create_session(sid, persona)
        session = {"persona_id": persona, "is_scam": False}
    
    # 3. Scam Detection
    if not session['is_scam']:
        # If logic fails, default to True (Safety)
        if logic.detect_scam(msg_text):
            pass 
        else:
            return {"status": "success", "reply": "I am not interested."}
            
    # 4. Generate Reply
    history = database.get_history(sid)
    # Ensure persona_id exists
    pid = session.get('persona_id', 'grandma')
    reply = logic.generate_reply(msg_text, history, pid)
    
    # 5. Background Task
    bg_tasks.add_task(background_tasks_handler, sid, msg_text, reply)
    
    return {"status": "success", "reply": reply}

# --- 5. ROOT ENDPOINT (Fixes 'Not Found') ---
@app.get("/")
def home():
    return {"status": "ONLINE", "message": "Sentinel System is Active. POST to /api/chat"}

# Run for local testing
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
