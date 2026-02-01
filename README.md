# 🛡️ Sentinel: Polymorphic Agentic Honey-Pot

> **Winner-Level Prototype for HCL GUVI India AI Buildathon**
> *Advanced Scam Detection, Multi-Persona Engagement, and Asynchronous Intelligence Extraction.*

## 🚀 The Problem
Traditional honeypots are static. Scammers realize they are talking to a bot and disconnect. To catch them, we need a system that feels **human**, **unpredictable**, and **vulnerable**.

## 💡 The Solution: Polymorphism
**Sentinel** is not just a chatbot. It is a **State Machine** that randomly assigns a unique "Persona" to each scammer session.
- **Session A** might meet *Mrs. Higgins* (Confused Grandma).
- **Session B** might meet *Rohan* (Broke Student).
- **Session C** might meet *Mr. Verma* (Angry Uncle).

This prevents scammers from detecting the pattern, maximizing **Engagement Duration** and **Intel Extraction**.

## 🛠️ Tech Stack
- **Engine:** FastAPI (Python) - *Chosen for <200ms latency.*
- **Brain:** Google Gemini 1.5 Flash - *Context-aware roleplay.*
- **Memory:** SQLite + Pandas - *Session state management.*
- **UI:** Streamlit - *Real-time "War Room" dashboard.*
- **Architecture:** Asynchronous Background Tasks (The API replies instantly; AI thinks in the background).

## ⚡ How to Run
1. Clone the repo.
2. Install requirements: `pip install -r requirements.txt`
3. Run the API: `uvicorn main:app --reload`
4. Run the Dashboard: `streamlit run dashboard.py`

## 📊 Unique Features
1. **Hybrid Extraction:** Uses Regex for speed + AI for cleaning complex data.
2. **Auto-Report:** Automatically pushes intelligence to GUVI endpoint when high-value data (UPI/Links) is found.
3. **Live Visualization:** Real-time monitoring of scammer conversations.