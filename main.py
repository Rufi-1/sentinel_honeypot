# main.py
from fastapi import FastAPI, Header, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import requests
import database
import logic

app = FastAPI(title="Sentinel Polymorphic Node")

class Msg(BaseModel):
    sender: str
    text: str
    timestamp: str

class Payload(BaseModel):
    sessionId: str
    message: Msg
    conversationHistory: List[Msg]
    metadata: Optional[dict] = None

# --- BACKGROUND WORKER ---
def background_tasks_handler(session_id, user_text, agent_text):
    # 1. Save Chat
    database.save_message(session_id, "scammer", user_text)
    database.save_message(session_id, "agent", agent_text)
    
    # 2. Extract Intel
    combined_text = f"{user_text} {agent_text}"
    intel = logic.extract_intel(combined_text)
    final_intel = database.update_intel(session_id, intel)
    
    # 3. Check Protocol: Report to GUVI?
    # Report if we found a Link/UPI OR if chat is long (>4 msgs)
    session = database.get_session(session_id)
    if final_intel['phishingLinks'] or final_intel['upiIds'] or len(database.get_history(session_id)) > 4:
        try:
            requests.post(
                "https://hackathon.guvi.in/api/updateHoneyPotFinalResult",
                json={
                    "sessionId": session_id,
                    "scamDetected": True,
                    "totalMessagesExchanged": len(database.get_history(session_id)),
                    "extractedIntelligence": final_intel,
                    "agentNotes": f"Polymorphic Persona: {session.get('persona_id')}"
                },
                timeout=1 # Fire and forget
            )
            print(f"✅ REPORTED {session_id}")
        except:
            pass 

@app.post("/api/chat")
async def chat_endpoint(payload: Payload, bg_tasks: BackgroundTasks, x_api_key: str = Header(None)):
    # Security
    if x_api_key != "my-secret-key":
        raise HTTPException(401, "Unauthorized")
    
    sid = payload.sessionId
    msg = payload.message.text
    
    # 1. Get/Create Session (Assign Random Persona)
    session = database.get_session(sid)
    if not session:
        persona = logic.select_random_persona()
        database.create_session(sid, persona)
        session = {"persona_id": persona, "is_scam": False}
    
    # 2. Guard: Detect Scam
    if not session['is_scam']:
        if logic.detect_scam(msg):
            # Update DB (pseudo-code, in real app add update function)
            pass 
        else:
            return {"status": "success", "reply": "I am not interested."}
            
    # 3. Actor: Generate Reply
    history = database.get_history(sid)
    reply = logic.generate_reply(msg, history, session['persona_id'])
    
    # 4. Async Work (Speed)
    bg_tasks.add_task(background_tasks_handler, sid, msg, reply)
    
    return {"status": "success", "reply": reply}