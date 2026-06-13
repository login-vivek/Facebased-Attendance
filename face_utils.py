import os
import cv2
import torch
import numpy as np
import pickle
from PIL import Image
from facenet_pytorch import MTCNN
from torchvision import transforms
from config import Config
from models import EnhancedSiameseNetwork
import pandas as pd
import matplotlib.pyplot as plt

# Initialize global device
DEVICE = Config.DEVICE

# Pre-load MTCNN detector for efficiency
mtcnn_detector = MTCNN(
    keep_all=True,
    device=DEVICE,
    min_face_size=60,
    thresholds=[0.6, 0.7, 0.8],
    factor=0.709,
    post_process=True
)

# Define the standard transformation for the Siamese Network input
RECOGNITION_TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5])
])


def calculate_iou(box1, box2):
    """Calculate Intersection over Union for two bounding boxes"""
    box1 = [float(x) for x in box1]
    box2 = [float(x) for x in box2]

    x_left = max(box1[0], box2[0])
    y_top = max(box1[1], box2[1])
    x_right = min(box1[2], box2[2])
    y_bottom = min(box1[3], box2[3])

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    intersection_area = (x_right - x_left) * (y_bottom - y_top)

    box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union_area = box1_area + box2_area - intersection_area

    return intersection_area / union_area if union_area > 0 else 0


def preprocess_image_for_detection(image_np):
    """Apply preprocessing (CLAHE, sharpening) to improve face detection quality.
       Expects a NumPy array (RGB).
    """
    if image_np is None:
        return None

    # Apply adaptive histogram equalization to improve contrast
    lab = cv2.cvtColor(image_np, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    cl = clahe.apply(l)
    enhanced_lab = cv2.merge((cl, a, b))
    enhanced_img = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2RGB)

    # Apply slight sharpening
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpened_img = cv2.filter2D(enhanced_img, -1, kernel)

    return sharpened_img


def enhance_face_crop(face_img_np):
    """Apply face-specific enhancements (CLAHE, denoising) to a face crop.
       Expects a NumPy array (RGB).
    """
    if face_img_np is None:
        return None

    # Convert to LAB for contrast enhancement
    face_lab = cv2.cvtColor(face_img_np, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(face_lab)

    # Apply CLAHE to L channel
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    cl = clahe.apply(l)

    # Merge back
    enhanced_lab = cv2.merge((cl, a, b))
    enhanced_face = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2RGB)

    # Apply mild denoising
    enhanced_face = cv2.fastNlMeansDenoisingColored(enhanced_face, None, 5, 5, 7, 21)

    return enhanced_face


def detect_and_crop_faces(image_path, classroom_id):
    """
    Detects and crops faces from a group photo using MTCNN.
    Saves temporary face images for a specific classroom and returns their data.
    """
    print(f"Detecting faces in {image_path} for classroom {classroom_id}...")

    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Image not found at {image_path}")

    rgb_image = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(rgb_image)

    # Preprocess image for better detection
    enhanced_img_np = preprocess_image_for_detection(rgb_image)
    enhanced_pil_image = Image.fromarray(enhanced_img_np) if enhanced_img_np is not None else pil_image

    # Detect faces on both original and enhanced images, then combine/filter
    boxes_orig, probs_orig = mtcnn_detector.detect(pil_image)
    boxes_enhanced, probs_enhanced = mtcnn_detector.detect(enhanced_pil_image)

    all_boxes = []
    all_probs = []

    # Collect high-confidence detections from original
    if boxes_orig is not None:
        for box, prob in zip(boxes_orig, probs_orig):
            if prob > 0.95: # High confidence
                all_boxes.append(box)
                all_probs.append(prob)

    # Collect high-confidence detections from enhanced, avoiding duplicates
    if boxes_enhanced is not None:
        for box, prob in zip(boxes_enhanced, probs_enhanced):
            if prob > 0.95:
                is_new = True
                for existing_box in all_boxes:
                    iou = calculate_iou(box, existing_box)
                    if iou > 0.5: # If significant overlap, it's not a new face
                        is_new = False
                        break
                if is_new:
                    all_boxes.append(box)
                    all_probs.append(prob)

    if not all_boxes:
        print("No faces detected in the group photo with sufficient confidence.")
        return []

    all_boxes = np.array(all_boxes)
    print(f"Detected {len(all_boxes)} unique faces.")

    face_data = [] # Data about detected faces (temp_id, bbox, path)
    
    # Directory for storing initially detected (temp) faces for this classroom
    temp_face_output_dir = os.path.join(Config.DATASETS_FOLDER, classroom_id, "temp_faces")
    os.makedirs(temp_face_output_dir, exist_ok=True)

    # Assign temporary IDs and save faces
    for i, box in enumerate(all_boxes):
        x1, y1, x2, y2 = map(int, box)

        # Add padding to face crop
        face_width = x2 - x1
        face_height = y2 - y1
        pad_x = int(face_width * 0.15)
        pad_y = int(face_height * 0.15)

        x1_padded, y1_padded = max(0, x1 - pad_x), max(0, y1 - pad_y)
        x2_padded, y2_padded = min(rgb_image.shape[1], x2 + pad_x), min(rgb_image.shape[0], y2 + pad_y)

        face_crop_np = rgb_image[y1_padded:y2_padded, x1_padded:x2_padded]
        if face_crop_np.size == 0: # Skip empty crops
            continue

        face_pil = Image.fromarray(face_crop_np)

        # Create a unique temporary ID for each face
        temp_face_id = f"temp_{i:03d}"
        face_path = os.path.join(temp_face_output_dir, f"{temp_face_id}.jpg")
        face_pil.save(face_path)

        face_data.append({
            "face_id": temp_face_id,
            "image_path": face_path,
            "bbox": [int(x1), int(y1), int(x2), int(y2)] # Original non-padded bbox
        })
    
    print(f"Temporary detected faces saved to {temp_face_output_dir}")
    return face_data


def load_face_recognition_model(classroom_id):
    """Load the trained model and embeddings for a specific classroom."""
    model_path = os.path.join(Config.MODELS_FOLDER, classroom_id, 'siamese_model_best.pth')
    embedding_dict_path = os.path.join(Config.EMBEDDINGS_FOLDER, classroom_id, 'embedding_dict.pkl')
    label_embeddings_path = os.path.join(Config.EMBEDDINGS_FOLDER, classroom_id, 'label_embeddings.pkl')

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model file not found for classroom '{classroom_id}' at: {model_path}")
    if not os.path.exists(embedding_dict_path):
        raise FileNotFoundError(f"Embedding dictionary not found for classroom '{classroom_id}' at: {embedding_dict_path}")
    if not os.path.exists(label_embeddings_path):
        raise FileNotFoundError(f"Label embeddings not found for classroom '{classroom_id}' at: {label_embeddings_path}")

    # Load the model
    print(f"Loading trained model for classroom {classroom_id}...")
    model = EnhancedSiameseNetwork().to(DEVICE)
    model.load_state_dict(torch.load(model_path, map_location=DEVICE))
    model.eval()

    # Load embeddings
    print(f"Loading face embeddings for classroom {classroom_id}...")
    with open(embedding_dict_path, 'rb') as f:
        embedding_dict = pickle.load(f)

    with open(label_embeddings_path, 'rb') as f:
        label_embeddings = pickle.load(f)

    return model, embedding_dict, label_embeddings


def recognize_faces_in_photo(image_path, classroom_id):
    """
    Performs face detection and recognition on a given photo using a trained model
    for a specific classroom.
    """
    print(f"\nPerforming face recognition on: {image_path} for classroom: {classroom_id}")

    try:
        model, embedding_dict, label_embeddings = load_face_recognition_model(classroom_id)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return {"error": str(e), "status": "model_not_found"}

    # Load the original image for drawing
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"Image not found at {image_path}")
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    # Preprocess the image for detection
    enhanced_img_np = preprocess_image_for_detection(rgb_image)
    
    pil_image = Image.fromarray(rgb_image)
    enhanced_pil = Image.fromarray(enhanced_img_np) if enhanced_img_np is not None else pil_image

    # Detect faces using both original and preprocessed images
    boxes_orig, probs_orig = mtcnn_detector.detect(pil_image)
    boxes_enhanced, probs_enhanced = mtcnn_detector.detect(enhanced_pil)

    all_boxes = []
    all_probs = []

    if boxes_orig is not None:
        for box, prob in zip(boxes_orig, probs_orig):
            if prob > 0.97:  # High confidence threshold
                all_boxes.append(box)
                all_probs.append(prob)

    if boxes_enhanced is not None:
        for box, prob in zip(boxes_enhanced, probs_enhanced):
            if prob > 0.97:
                is_new = True
                for existing_box in all_boxes:
                    iou = calculate_iou(box, existing_box)
                    if iou > 0.5:  # If significant overlap
                        is_new = False
                        break
                if is_new:
                    all_boxes.append(box)
                    all_probs.append(prob)

    if not all_boxes:
        print("No faces detected with sufficient confidence for recognition.")
        return {"recognized_faces": [], "image_url": None, "message": "No faces detected."}

    all_boxes = np.array(all_boxes)
    print(f"Detected {len(all_boxes)} faces in the image for recognition.")

    recognized_faces_data = []
    
    # Prepare image for drawing bounding boxes and labels
    img_with_boxes = image.copy() # Use a copy to draw on

    # Process each detected face
    for i, box in enumerate(all_boxes):
        x1, y1, x2, y2 = map(int, box)

        # Dynamic padding to face crop
        face_width = x2 - x1
        face_height = y2 - y1
        pad_x = int(face_width * 0.15)
        pad_y = int(face_height * 0.15)

        x1_padded, y1_padded = max(0, x1 - pad_x), max(0, y1 - pad_y)
        x2_padded, y2_padded = min(rgb_image.shape[1], x2 + pad_x), min(rgb_image.shape[0], y2 + pad_y)

        # Extract face crop (using RGB image for consistent color)
        face_crop_np = rgb_image[y1_padded:y2_padded, x1_padded:x2_padded]
        if face_crop_np.size == 0:
            continue

        face_pil = Image.fromarray(face_crop_np)

        # Enhance face quality
        face_enhanced_np = enhance_face_crop(face_crop_np)
        face_pil_enhanced = Image.fromarray(face_enhanced_np)

        # Generate multiple embeddings for robust recognition
        embeddings = []
        with torch.no_grad():
            # Original face
            img_tensor = RECOGNITION_TRANSFORM(face_pil).unsqueeze(0).to(DEVICE)
            embeddings.append(model(img_tensor).squeeze().cpu().numpy())

            # Enhanced face
            img_tensor_enhanced = RECOGNITION_TRANSFORM(face_pil_enhanced).unsqueeze(0).to(DEVICE)
            embeddings.append(model(img_tensor_enhanced).squeeze().cpu().numpy())

            # Horizontally flipped face
            flipped_face_pil = transforms.functional.hflip(face_pil)
            img_tensor_flipped = RECOGNITION_TRANSFORM(flipped_face_pil).unsqueeze(0).to(DEVICE)
            embeddings.append(model(img_tensor_flipped).squeeze().cpu().numpy())

        # Average the embeddings for the current detected face
        face_embedding = np.mean(embeddings, axis=0)
        face_embedding = face_embedding / np.linalg.norm(face_embedding)  # Normalize

        # Ensemble method for recognition
        results = []

        # Method 1: Compare with average embeddings
        for label, ref_embedding in embedding_dict.items():
            similarity = np.dot(face_embedding, ref_embedding)
            results.append((label, similarity, "avg"))

        # Method 2: Compare with each individual embedding and take maximum
        for label, ref_embeddings_list in label_embeddings.items():
            if ref_embeddings_list:
                similarities = [np.dot(face_embedding, ref_emb) for ref_emb in ref_embeddings_list]
                max_similarity = max(similarities)
                results.append((label, max_similarity, "max"))

        # Sort by similarity score
        results.sort(key=lambda x: x[1], reverse=True)

        # Get top matches from both methods
        avg_matches = [r for r in results if r[2] == "avg"][:3]
        max_matches = [r for r in results if r[2] == "max"][:3]

        # Weighted ensemble of both methods
        final_scores = {}
        for label, score, method in avg_matches + max_matches:
            if label not in final_scores:
                final_scores[label] = 0
            # Weight the "avg" method slightly higher
            weight = 1.2 if method == "avg" else 1.0
            final_scores[label] += score * weight

        # Get the highest scoring label
        if final_scores:
            most_similar_face, highest_score = max(final_scores.items(), key=lambda x: x[1])
            highest_score_normalized = highest_score / (1.2 * len(avg_matches) + 1.0 * len(max_matches))
            highest_score_normalized = min(highest_score_normalized, 1.0)
        else:
            most_similar_face, highest_score_normalized = None, 0

        roll_number = "Unknown"
        confidence = "Low"
        
        if most_similar_face and highest_score_normalized >= Config.RECOGNITION_CONFIDENCE_THRESHOLD:
            roll_number = most_similar_face
            confidence = f"{highest_score_normalized:.2f}"
            print(f"Face #{i+1} recognized as Roll: {roll_number} (confidence: {confidence})")
        else:
            print(f"Face #{i+1} identified as Unknown (confidence: {highest_score_normalized:.4f})")

        # Draw bounding box and label on the original image
        cv2.rectangle(img_with_boxes, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label_text = f"Roll: {roll_number} ({confidence})"

        # Improve text visibility with background
        text_size, _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(img_with_boxes, (x1, y1 - 30), (x1 + text_size[0], y1), (0, 255, 0), -1)
        cv2.putText(img_with_boxes, label_text, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

        # Save the detected face crop
        face_filename = os.path.join(Config.RECOGNIZED_FACES_FOLDER, f"face_{classroom_id}_{roll_number}_{i}.jpg")
        Image.fromarray(cv2.cvtColor(face_enhanced_np, cv2.COLOR_RGB2BGR)).save(face_filename)

        recognized_faces_data.append({
            "bbox": [x1, y1, x2, y2],
            "roll_number": roll_number,
            "confidence": float(highest_score_normalized),
            "face_image_url": f"/recognized_faces/{os.path.basename(face_filename)}"
        })

    # Save the annotated image
    timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
    result_filename = os.path.join(Config.OUTPUT_IMAGES_FOLDER, f"recognition_result_{classroom_id}_{timestamp}.jpg")
    cv2.imwrite(result_filename, img_with_boxes)
    print(f"Annotated image saved as '{result_filename}'")
    
    image_url = f"/output_images/{os.path.basename(result_filename)}"

    return {"recognized_faces": recognized_faces_data, "image_url": image_url, "message": "Faces recognized successfully."}