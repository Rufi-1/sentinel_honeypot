# database.py
import sqlite3
import json
import pandas as pd

DB_NAME = "honeypot.db"

def init_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sessions 
                 (session_id TEXT PRIMARY KEY, is_scam BOOLEAN, msg_count INTEGER, persona_id TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages 
                 (session_id TEXT, sender TEXT, text TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS intelligence 
                 (session_id TEXT PRIMARY KEY, data TEXT)''')
    conn.commit()
    conn.close()

# Init on load
init_db()

# --- CORE FUNCTIONS ---
def create_session(session_id, persona_id):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO sessions VALUES (?, ?, ?, ?)", (session_id, False, 0, persona_id))
    empty_intel = json.dumps({"bankAccounts": [], "upiIds": [], "phishingLinks": [], "phoneNumbers": [], "suspiciousKeywords": []})
    c.execute("INSERT OR IGNORE INTO intelligence VALUES (?, ?)", (session_id, empty_intel))
    conn.commit()
    conn.close()

def get_session(session_id):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"session_id": row[0], "is_scam": row[1], "msg_count": row[2], "persona_id": row[3]}
    return None

def save_message(session_id, sender, text):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT INTO messages (session_id, sender, text) VALUES (?, ?, ?)", (session_id, sender, text))
    conn.commit()
    conn.close()

def get_history(session_id):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT sender, text FROM messages WHERE session_id=?", (session_id,))
    rows = c.fetchall()
    conn.close()
    return [{"sender": r[0], "text": r[1]} for r in rows]

def update_intel(session_id, new_data):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT data FROM intelligence WHERE session_id=?", (session_id,))
    row = c.fetchone()
    current_data = json.loads(row[0]) if row else {}
    
    # Merge unique data
    for key, val in new_data.items():
        existing = set(current_data.get(key, []))
        existing.update(val)
        current_data[key] = list(existing)
        
    c.execute("UPDATE intelligence SET data=? WHERE session_id=?", (json.dumps(current_data), session_id))
    conn.commit()
    conn.close()
    return current_data

# --- FOR DASHBOARD ---
def get_all_sessions_df():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    df = pd.read_sql_query("SELECT * FROM sessions", conn)
    conn.close()
    return df

def get_messages_df(session_id):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    df = pd.read_sql_query(f"SELECT * FROM messages WHERE session_id='{session_id}'", conn)
    conn.close()
    return df

def get_intel_raw(session_id):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT data FROM intelligence WHERE session_id=?", (session_id,))
    row = c.fetchone()
    conn.close()
    return json.loads(row[0]) if row else {}