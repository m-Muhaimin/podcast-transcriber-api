import sqlite3
import json

# Database setup
DB_PATH = "podcast_data.db"

def init_db():
    """Initializes the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS podcast_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transcript TEXT,
            summary TEXT,
            takeaways TEXT,  -- Stored as JSON
            quiz TEXT        -- Stored as JSON
        )
    """)
    conn.commit()
    conn.close()

def save_podcast_data(transcript: str, summary: str, takeaways: list, quiz: dict):
    """Saves podcast transcript, summary, key takeaways, and quiz into the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO podcast_data (transcript, summary, takeaways, quiz)
        VALUES (?, ?, ?, ?)
    """, (transcript, summary, json.dumps(takeaways), json.dumps(quiz)))
    
    conn.commit()
    conn.close()
    
def get_latest_podcast_data():
    """Fetches the latest podcast entry from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT summary, takeaways FROM podcast_data ORDER BY id DESC LIMIT 1")
    result = cursor.fetchone()
    conn.close()
    
    if result:
        summary, takeaways = result
        return {"summary": summary, "takeaways": json.loads(takeaways)}
    return None

def get_all_podcasts():
    """Fetches all podcast entries from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, summary, takeaways FROM podcast_data ORDER BY id DESC")
    results = cursor.fetchall()
    conn.close()
    
    podcast_data = []
    for summary, takeaways in results:
        podcast_data.append({"summary": summary, "takeaways": json.loads(takeaways)})
    return podcast_data

def get_podcast_by_id(podcast_id):
    """Fetches a podcast entry by ID from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT summary, takeaways FROM podcast_data WHERE id = ?", (podcast_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        summary, takeaways = result
        return {"summary": summary, "takeaways": json.loads(takeaways)}
    return None

# Initialize database
init_db()
