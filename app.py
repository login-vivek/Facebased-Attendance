from flask import Flask, request, jsonify
from flask_cors import CORS
from deepface import DeepFace
from database import init_db, get_all_persons, get_today_attendance, log_attendance
import cv2
import sqlite3
import os
import base64
import numpy as np
import shutil
from datetime import datetime

app = Flask(__name__)
CORS(app, origins="*", allow_headers="*", methods=["GET", "POST", "DELETE", "OPTIONS"])

@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        response = jsonify({})
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
        return response

@app.after_request
def add_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
    response.headers['ngrok-skip-browser-warning'] = 'true'
    return response

DB_PATH   = "attendance.db"
FACES_DIR = "faces"
THRESHOLD = 0.6

init_db()


# ──────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────

def base64_to_image(b64_string):
    if "," in b64_string:
        b64_string = b64_string.split(",")[1]
    img_data = base64.b64decode(b64_string)
    np_arr   = np.frombuffer(img_data, np.uint8)
    return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)


def get_enrolled():
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.name, p.employee_id, f.photo_path
        FROM persons p
        JOIN face_photos f ON p.id = f.person_id
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


# ──────────────────────────────────────────
#  BASIC
# ──────────────────────────────────────────

@app.route("/")
def home():
    return jsonify({"status": "FaceAttend API running!"})


# ──────────────────────────────────────────
#  PERSONS
# ──────────────────────────────────────────

@app.route("/persons", methods=["GET"])
def persons():
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, employee_id, department, role FROM persons")
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        result.append({
            "id":          row[0],
            "name":        row[1],
            "employee_id": row[2],
            "department":  row[3],
            "role":        row[4],
            "email":       ""
        })
    return jsonify(result)


# ──────────────────────────────────────────
#  DELETE PERSON
# ──────────────────────────────────────────

@app.route("/persons/<employee_id>", methods=["DELETE"])
def delete_person(employee_id):
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM persons WHERE employee_id = ?", (employee_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": f"No person found with ID: {employee_id}"}), 404
    person_name = row[0]
    try:
        cursor.execute("DELETE FROM face_photos WHERE employee_id = ?", (employee_id,))
        cursor.execute("DELETE FROM persons WHERE employee_id = ?", (employee_id,))
        conn.commit()
        conn.close()
        folder = os.path.join(FACES_DIR, employee_id)
        if os.path.exists(folder):
            shutil.rmtree(folder)
        print(f"[DELETE] Removed: {person_name} ({employee_id})")
        return jsonify({
            "success":     True,
            "message":     f"{person_name} removed from the system",
            "employee_id": employee_id
        })
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


# ──────────────────────────────────────────
#  ATTENDANCE
# ──────────────────────────────────────────

@app.route("/attendance", methods=["GET"])
def attendance():
    date_filter = request.args.get("date", "").strip()
    conn        = sqlite3.connect(DB_PATH)
    cursor      = conn.cursor()
    if date_filter:
        cursor.execute(
            "SELECT * FROM attendance_log WHERE date = ? ORDER BY check_in DESC",
            (date_filter,)
        )
    else:
        today = datetime.today().date().isoformat()
        cursor.execute(
            "SELECT * FROM attendance_log WHERE date = ? ORDER BY check_in DESC",
            (today,)
        )
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        result.append({
            "id":          row[0],
            "person_id":   row[1],
            "employee_id": row[2],
            "name":        row[3],
            "check_in":    row[4],
            "date":        row[5],
            "status":      row[6],
            "confidence":  row[7]
        })
    return jsonify(result)


# ──────────────────────────────────────────
#  STATS
# ──────────────────────────────────────────

@app.route("/stats", methods=["GET"])
def stats():
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today  = datetime.today().date().isoformat()
    cursor.execute("SELECT COUNT(*) FROM persons")
    total = cursor.fetchone()[0]
    cursor.execute(
        "SELECT COUNT(*) FROM attendance_log WHERE date = ? AND status = 'Present'",
        (today,)
    )
    present = cursor.fetchone()[0]
    cursor.execute(
        "SELECT COUNT(*) FROM attendance_log WHERE date = ? AND status = 'Late'",
        (today,)
    )
    late = cursor.fetchone()[0]
    conn.close()
    return jsonify({
        "total_enrolled": total,
        "present_today":  present,
        "late_today":     late,
        "absent_today":   max(0, total - present - late),
        "date":           today
    })


# ──────────────────────────────────────────
#  ENROLL
# ──────────────────────────────────────────

@app.route("/enroll", methods=["POST"])
def enroll():
    data        = request.json
    name        = data.get("name")
    employee_id = data.get("employee_id")
    department  = data.get("department", "")
    role        = data.get("role", "")
    photos      = data.get("photos", [])
    if not name or not employee_id or not photos:
        return jsonify({"error": "name, employee_id and photos are required"}), 400
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO persons (name, employee_id, department, role)
            VALUES (?, ?, ?, ?)
        """, (name, employee_id, department, role))
        conn.commit()
        person_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": f"ID '{employee_id}' already exists"}), 409
    person_dir = os.path.join(FACES_DIR, employee_id)
    os.makedirs(person_dir, exist_ok=True)
    saved = 0
    for i, photo_b64 in enumerate(photos):
        try:
            img  = base64_to_image(photo_b64)
            path = os.path.join(person_dir, f"{i + 1}.jpg")
            cv2.imwrite(path, img)
            cursor.execute("""
                INSERT INTO face_photos (person_id, employee_id, photo_path)
                VALUES (?, ?, ?)
            """, (person_id, employee_id, path))
            saved += 1
        except Exception as e:
            print(f"[ENROLL] Photo {i + 1} error: {e}")
    conn.commit()
    conn.close()
    return jsonify({
        "success":   True,
        "message":   f"{name} enrolled successfully with {saved} photo(s)!",
        "person_id": person_id
    })


# ──────────────────────────────────────────
#  RECOGNIZE
# ──────────────────────────────────────────

@app.route("/recognize", methods=["POST"])
def recognize():
    data            = request.json
    image_b64       = data.get("image")
    override_status = data.get("status", None)
    if not image_b64:
        return jsonify({"error": "No image provided"}), 400
    frame     = base64_to_image(image_b64)
    temp_path = "temp_recognize.jpg"
    cv2.imwrite(temp_path, frame)
    enrolled = get_enrolled()
    if not enrolled:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"error": "No enrolled faces found. Enroll someone first."}), 404
    best_match    = None
    best_distance = 999
    for person_id, name, employee_id, photo_path in enrolled:
        if not os.path.exists(photo_path):
            continue
        try:
            result   = DeepFace.verify(
                img1_path=temp_path,
                img2_path=photo_path,
                model_name="VGG-Face",
                enforce_detection=False
            )
            distance = result["distance"]
            if distance < best_distance:
                best_distance = distance
                best_match    = (person_id, name, employee_id)
        except Exception as e:
            print(f"[RECOGNIZE] Error: {e}")
            continue
    if os.path.exists(temp_path):
        os.remove(temp_path)
    if best_match and best_distance < THRESHOLD:
        person_id, name, employee_id = best_match
        confidence = round((1 - best_distance) * 100, 1)
        if override_status in ("Present", "Late"):
            status = override_status
        else:
            hour   = datetime.now().hour
            status = "Late" if hour >= 9 else "Present"
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        today  = datetime.today().date().isoformat()
        now    = datetime.now().strftime("%H:%M:%S")
        cursor.execute(
            "SELECT id FROM attendance_log WHERE employee_id = ? AND date = ?",
            (employee_id, today)
        )
        existing = cursor.fetchone()
        if not existing:
            cursor.execute("""
                INSERT INTO attendance_log
                    (person_id, employee_id, name, date, check_in, status, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (person_id, employee_id, name, today, now, status, confidence))
            conn.commit()
            attendance_logged = True
        else:
            attendance_logged = False
        conn.close()
        return jsonify({
            "recognized":        True,
            "name":              name,
            "employee_id":       employee_id,
            "confidence":        confidence,
            "status":            status,
            "attendance_logged": attendance_logged
        })
    return jsonify({
        "recognized": False,
        "message":    "Face not recognized"
    })


# ──────────────────────────────────────────
#  RUN
# ──────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 45)
    print("  FaceAttend API starting...")
    print(f"  Running on port {port}")
    print("=" * 45)
    app.run(debug=False, host="0.0.0.0", port=port)