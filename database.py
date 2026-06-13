import sqlite3
import os

DB_PATH = "attendance.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS persons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            employee_id TEXT UNIQUE NOT NULL,
            department TEXT,
            role TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER,
            employee_id TEXT,
            name TEXT,
            check_in TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            date TEXT,
            status TEXT DEFAULT 'Present',
            confidence REAL,
            FOREIGN KEY (person_id) REFERENCES persons(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS face_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER,
            employee_id TEXT,
            photo_path TEXT,
            FOREIGN KEY (person_id) REFERENCES persons(id)
        )
    ''')

    conn.commit()
    conn.close()
    print("Database ready!")

def get_all_persons():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM persons")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_today_attendance():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today = __import__('datetime').date.today().isoformat()
    cursor.execute("SELECT * FROM attendance_log WHERE date=?", (today,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def log_attendance(person_id, employee_id, name, status, confidence):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today = __import__('datetime').date.today().isoformat()

    cursor.execute("SELECT id FROM attendance_log WHERE employee_id=? AND date=?",
                   (employee_id, today))
    existing = cursor.fetchone()

    if not existing:
        cursor.execute('''
            INSERT INTO attendance_log (person_id, employee_id, name, date, status, confidence)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (person_id, employee_id, name, today, status, confidence))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

if __name__ == "__main__":
    init_db()
    