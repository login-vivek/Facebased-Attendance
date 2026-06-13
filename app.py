import os
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import uuid
import json # For handling roll number assignment data
import shutil # For moving files

# Import your modules
from config import Config
from face_utils import detect_and_crop_faces, recognize_faces_in_photo
from train import augment_faces, train_siamese_network_for_classroom

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

# --- Helper functions ---
# In your allowed_file function
def allowed_file(filename):
    if not '.' in filename:
        return False
    # Get the part after the last dot, and add a leading dot back
    ext = '.' + filename.rsplit('.', 1)[1].lower()
    return ext in app.config['ALLOWED_EXTENSIONS']

def classroom_model_exists(classroom_id):
    """Checks if a trained model exists for the given classroom ID."""
    model_path = os.path.join(app.config['MODELS_FOLDER'], classroom_id, 'siamese_model_best.pth')
    return os.path.exists(model_path)

# --- Flask Routes ---

@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Face Recognition Flask API is running!"})

@app.route('/classroom/<classroom_id>/detect_faces', methods=['POST'])
def detect_faces_api(classroom_id):
    """
    Endpoint to upload a group photo and detect faces,
    assigning temporary IDs.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Save to a temporary upload folder
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            # Call the detection utility function
            face_data = detect_and_crop_faces(filepath, classroom_id)
            
            # Remove the uploaded group photo after processing
            os.remove(filepath)

            if not face_data:
                return jsonify({"message": "No faces detected in the photo.", "faces": []}), 200

            # Prepare response: provide temp face ID, bounding box, and a URL for the cropped face
            response_faces = []
            for face_info in face_data:
                face_image_filename = os.path.basename(face_info['image_path'])
                response_faces.append({
                    "face_id": face_info['face_id'],
                    "bbox": face_info['bbox'],
                    "face_image_url": f"/datasets/{classroom_id}/temp_faces/{face_image_filename}"
                })
            
            return jsonify({
                "message": f"Successfully detected {len(response_faces)} faces.",
                "classroom_id": classroom_id,
                "faces": response_faces
            }), 200
        except Exception as e:
            # Clean up the uploaded file in case of an error
            if os.path.exists(filepath):
                os.remove(filepath)
            app.logger.error(f"Error during face detection for {classroom_id}: {e}", exc_info=True)
            return jsonify({"error": f"Internal server error during face detection: {str(e)}"}), 500
    else:
        return jsonify({"error": "File type not allowed"}), 400

@app.route('/classroom/<classroom_id>/assign_roll_numbers', methods=['POST'])
def assign_roll_numbers_api(classroom_id):
    """
    Endpoint to assign roll numbers to detected temporary faces.
    Expects JSON body: `{"assignments": [{"face_id": "temp_001", "roll_number": "Roll_001"}, ...]}`
    """
    data = request.get_json()
    if not data or 'assignments' not in data:
        return jsonify({"error": "Invalid request body. Expected {'assignments': [{'face_id': '...', 'roll_number': '...'}]}"}), 400

    assignments = data['assignments']
    if not assignments:
        return jsonify({"message": "No assignments provided."}), 200

    temp_faces_dir = os.path.join(app.config['DATASETS_FOLDER'], classroom_id, "temp_faces")
    labeled_faces_dir = os.path.join(app.config['DATASETS_FOLDER'], classroom_id, "labeled_faces")
    os.makedirs(labeled_faces_dir, exist_ok=True)

    successful_assignments = []
    failed_assignments = []

    for assignment in assignments:
        face_id = assignment.get('face_id')
        roll_number = assignment.get('roll_number')

        if not face_id or not roll_number:
            failed_assignments.append({"assignment": assignment, "reason": "Missing face_id or roll_number"})
            continue

        temp_face_filename = f"{face_id}.jpg"
        temp_face_path = os.path.join(temp_faces_dir, temp_face_filename)

        if os.path.exists(temp_face_path):
            # Move and rename the file
            new_filename = f"{roll_number}.jpg"
            new_face_path = os.path.join(labeled_faces_dir, new_filename)
            try:
                shutil.move(temp_face_path, new_face_path)
                successful_assignments.append({"face_id": face_id, "roll_number": roll_number, "new_path": new_face_path})
            except Exception as e:
                failed_assignments.append({"assignment": assignment, "reason": f"File move error: {str(e)}"})
        else:
            failed_assignments.append({"assignment": assignment, "reason": f"Temporary face image not found: {temp_face_path}"})
    
    # Optionally, remove the temp_faces directory if all are moved
    if os.path.exists(temp_faces_dir) and not os.listdir(temp_faces_dir):
        os.rmdir(temp_faces_dir)

    return jsonify({
        "message": f"Assigned {len(successful_assignments)} roll numbers.",
        "successful": successful_assignments,
        "failed": failed_assignments
    }), 200


@app.route('/classroom/<classroom_id>/train_model', methods=['POST'])
def train_model_api(classroom_id):
    """
    Endpoint to trigger the training of the Siamese Network for a given classroom.
    """
    if classroom_model_exists(classroom_id):
        return jsonify({"message": f"Model for classroom '{classroom_id}' already trained. To retrain, delete existing model files."}), 200

    try:
        # Collect all labeled images for this classroom
        labeled_faces_dir = os.path.join(app.config['DATASETS_FOLDER'], classroom_id, "labeled_faces")
        if not os.path.exists(labeled_faces_dir) or not os.listdir(labeled_faces_dir):
            return jsonify({"error": f"No labeled faces found for classroom {classroom_id}. Please assign roll numbers first."}), 400

        # Prepare face_data for augmentation (list of dicts with 'image_path' and 'label')
        face_data_for_augmentation = []
        for filename in os.listdir(labeled_faces_dir):
            if filename.lower().endswith(app.config['ALLOWED_EXTENSIONS']):
                label = os.path.splitext(filename)[0]
                face_data_for_augmentation.append({'image_path': os.path.join(labeled_faces_dir, filename), 'label': label})

        if not face_data_for_augmentation:
            return jsonify({"error": f"No valid labeled face images found in {labeled_faces_dir}."}), 400

        # Step 1: Augment faces
        augmented_data = augment_faces(face_data_for_augmentation, classroom_id)
        
        # Step 2: Train the model
        # train_siamese_network_for_classroom will handle combining original and augmented data internally
        training_result = train_siamese_network_for_classroom(classroom_id)

        return jsonify(training_result), 200
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        app.logger.error(f"Error during model training for {classroom_id}: {e}", exc_info=True)
        return jsonify({"error": f"Internal server error during training: {str(e)}"}), 500


@app.route('/classroom/<classroom_id>/recognize_faces', methods=['POST'])
def recognize_faces_api(classroom_id):
    """
    Endpoint to recognize faces in an attendance photo for a specific classroom.
    """
    if not classroom_model_exists(classroom_id):
        return jsonify({"error": f"No trained model found for classroom '{classroom_id}'. Please train the model first."}), 404

    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            # Perform face recognition
            recognition_results = recognize_faces_in_photo(filepath, classroom_id)
            if "image_url" in recognition_results:
                recognition_results["resultImage"] = recognition_results.pop("image_url")
            
            # Remove the uploaded photo after processing
            os.remove(filepath)

            return jsonify(recognition_results), 200
        except FileNotFoundError as fnf_e:
            return jsonify({"error": str(fnf_e), "status": "model_not_found"}), 404
        except Exception as e:
            if os.path.exists(filepath):
                os.remove(filepath)
            app.logger.error(f"Error during face recognition for {classroom_id}: {e}", exc_info=True)
            return jsonify({"error": f"Internal server error during recognition: {str(e)}"}), 500
    else:
        return jsonify({"error": "File type not allowed"}), 400


@app.route('/classroom/<classroom_id>/status', methods=['GET'])
def get_classroom_status(classroom_id):
    """
    Endpoint to check the training status of a classroom.
    """
    model_trained = classroom_model_exists(classroom_id)
    labeled_faces_dir = os.path.join(app.config['DATASETS_FOLDER'], classroom_id, "labeled_faces")
    labeled_faces_count = 0
    if os.path.exists(labeled_faces_dir):
        labeled_faces_count = len([f for f in os.listdir(labeled_faces_dir) if f.lower().endswith(app.config['ALLOWED_EXTENSIONS'])])

    return jsonify({
        "classroom_id": classroom_id,
        "model_trained": model_trained,
        "labeled_faces_count": labeled_faces_count,
        "message": "Model trained" if model_trained else "Model not yet trained."
    }), 200

# Serve static files (e.g., cropped faces, annotated images)
@app.route('/recognized_faces/<filename>')
def serve_recognized_face(filename):
    return send_from_directory(app.config['RECOGNIZED_FACES_FOLDER'], filename)

@app.route('/output_images/<filename>')
def serve_output_image(filename):
    return send_from_directory(app.config['OUTPUT_IMAGES_FOLDER'], filename)

@app.route('/datasets/<classroom_id>/temp_faces/<filename>')
def serve_temp_face(classroom_id, filename):
    return send_from_directory(os.path.join(app.config['DATASETS_FOLDER'], classroom_id, "temp_faces"), filename)


if __name__ == '__main__':
    app.run(debug=Config.DEBUG, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))