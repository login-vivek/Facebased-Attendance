import cv2
import os
import sqlite3
import sys

DB_PATH = "attendance.db"
FACES_DIR = "faces"

def enroll_person(name, employee_id, department="", role=""):
    os.makedirs(FACES_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO persons (name, employee_id, department, role)
            VALUES (?, ?, ?, ?)
        ''', (name, employee_id, department, role))
        conn.commit()
        person_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        print(f"ID {employee_id} already exists!")
        conn.close()
        return
    conn.close()

    person_dir = os.path.join(FACES_DIR, employee_id)
    os.makedirs(person_dir, exist_ok=True)

    print(f"\nEnrolling {name}...")
    print("Camera will open. Press SPACE to capture, Q to quit.")
    print("Capture 5 photos from slightly different angles.\n")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Cannot open camera!")
        return

    count = 0
    total = 5

    while count < total:
        ret, frame = cap.read()
        if not ret:
            break

        display = frame.copy()
        cv2.putText(display, f"Photo {count+1}/{total} - Press SPACE to capture",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(display, f"Enrolling: {name}",
                    (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        cv2.imshow("Enroll Face - Press SPACE to capture", display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord(' '):
            photo_path = os.path.join(person_dir, f"{count+1}.jpg")
            cv2.imwrite(photo_path, frame)

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO face_photos (person_id, employee_id, photo_path)
                VALUES (?, ?, ?)
            ''', (person_id, employee_id, photo_path))
            conn.commit()
            conn.close()

            print(f"Photo {count+1} captured!")
            count += 1

        elif key == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

    if count == total:
        print(f"\n✓ {name} enrolled successfully with {count} photos!")
    else:
        print(f"\nOnly {count} photos captured. Try enrolling again.")

if __name__ == "__main__":
    from database import init_db
    init_db()

    print("=== Face Enrollment ===")
    name = input("Enter full name: ")
    employee_id = input("Enter ID (e.g. EMP-001): ")
    department = input("Enter department: ")
    role = input("Enter role: ")

    enroll_person(name, employee_id, department, role)
