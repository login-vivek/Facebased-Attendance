import cv2
import os
import sqlite3
from deepface import DeepFace
from datetime import datetime

DB_PATH = "attendance.db"
FACES_DIR = "faces"
THRESHOLD = 0.6

def get_all_enrolled():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.id, p.name, p.employee_id, f.photo_path 
        FROM persons p
        JOIN face_photos f ON p.id = f.person_id
    ''')
    rows = cursor.fetchall()
    conn.close()
    return rows

def log_attendance(person_id, employee_id, name, confidence):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today = datetime.today().date().isoformat()
    now = datetime.now().strftime("%H:%M:%S")

    cursor.execute("SELECT id FROM attendance_log WHERE employee_id=? AND date=?",
                   (employee_id, today))
    existing = cursor.fetchone()

    if not existing:
        hour = datetime.now().hour
        status = "Late" if hour >= 9 else "Present"
        cursor.execute('''
            INSERT INTO attendance_log 
            (person_id, employee_id, name, date, check_in, status, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (person_id, employee_id, name, today, now, status, confidence))
        conn.commit()
        conn.close()
        return True, status
    conn.close()
    return False, "Already marked"

def recognize_face(frame, enrolled):
    temp_path = "temp_frame.jpg"
    cv2.imwrite(temp_path, frame)

    best_match = None
    best_distance = 999

    for person_id, name, employee_id, photo_path in enrolled:
        if not os.path.exists(photo_path):
            continue
        try:
            result = DeepFace.verify(
                img1_path=temp_path,
                img2_path=photo_path,
                model_name="VGG-Face",
                enforce_detection=False
            )
            distance = result["distance"]
            if distance < best_distance:
                best_distance = distance
                best_match = (person_id, name, employee_id, distance)
        except:
            continue

    if os.path.exists(temp_path):
        os.remove(temp_path)

    if best_match and best_distance < THRESHOLD:
        confidence = round((1 - best_distance) * 100, 1)
        return best_match[0], best_match[1], best_match[2], confidence
    return None, None, None, 0

def run_recognition():
    print("Loading enrolled faces...")
    enrolled = get_all_enrolled()

    if not enrolled:
        print("No enrolled faces found! Run enroll.py first.")
        return

    print(f"Loaded {len(set(e[2] for e in enrolled))} enrolled person(s)")
    print("Camera opening... Press Q to quit, SPACE to scan face\n")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Cannot open camera!")
        return

    last_result = ""
    last_color = (255, 255, 255)
    scan_cooldown = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        display = frame.copy()

        cv2.putText(display, "Press SPACE to scan face | Q to quit",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        if last_result:
            cv2.putText(display, last_result,
                        (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, last_color, 2)

        if scan_cooldown > 0:
            cv2.putText(display, f"Scanning... {scan_cooldown}",
                        (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
            scan_cooldown -= 1

        cv2.imshow("Face Attendance - Recognition", display)

        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break

        elif key == ord(' ') and scan_cooldown == 0:
            print("Scanning face...")
            scan_cooldown = 30

            person_id, name, employee_id, confidence = recognize_face(frame, enrolled)

            if name:
                logged, status = log_attendance(person_id, employee_id, name, confidence)
                if logged:
                    last_result = f"✓ {name} | {status} | {confidence}%"
                    last_color = (0, 255, 0)
                    print(f"✓ Attendance marked: {name} ({status}) - {confidence}% confidence")
                else:
                    last_result = f"Already marked: {name}"
                    last_color = (0, 165, 255)
                    print(f"Already marked today: {name}")
            else:
                last_result = "Face not recognized!"
                last_color = (0, 0, 255)
                print("Face not recognized!")

    cap.release()
    cv2.destroyAllWindows()
    print("\nRecognition stopped.")

if __name__ == "__main__":
    run_recognition()
