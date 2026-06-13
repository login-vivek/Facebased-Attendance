import os
import torch

class Config:
    # Base directory for the Flask app
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

    # On Render, use the mounted persistent disk if available.
    # Set PERSISTENT_DATA_DIR env var to override (e.g., /opt/render/project/src/persistent_data)
    PERSISTENT_DATA_DIR = os.environ.get('PERSISTENT_DATA_DIR', BASE_DIR)

    # Uploads directory (temp, ephemeral is fine)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Persistent data directories — stored on the mounted disk in production
    DATASETS_FOLDER = os.path.join(PERSISTENT_DATA_DIR, 'datasets')
    MODELS_FOLDER = os.path.join(PERSISTENT_DATA_DIR, 'models')
    EMBEDDINGS_FOLDER = os.path.join(PERSISTENT_DATA_DIR, 'embeddings')
    RECOGNIZED_FACES_FOLDER = os.path.join(PERSISTENT_DATA_DIR, 'recognized_faces')
    OUTPUT_IMAGES_FOLDER = os.path.join(PERSISTENT_DATA_DIR, 'output_images')

    # Ensure all necessary directories exist
    os.makedirs(DATASETS_FOLDER, exist_ok=True)
    os.makedirs(MODELS_FOLDER, exist_ok=True)
    os.makedirs(EMBEDDINGS_FOLDER, exist_ok=True)
    os.makedirs(RECOGNIZED_FACES_FOLDER, exist_ok=True)
    os.makedirs(OUTPUT_IMAGES_FOLDER, exist_ok=True)

    # Flask secret key — set SECRET_KEY env var in production
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

    # Allowed extensions for image uploads
    ALLOWED_EXTENSIONS = ('.png', '.jpg', '.jpeg')

    # Face recognition confidence threshold
    RECOGNITION_CONFIDENCE_THRESHOLD = 0.3

    # Device for PyTorch — Render free tier has no GPU
    DEVICE = 'cuda' if os.environ.get('USE_CUDA', 'false').lower() == 'true' and torch.cuda.is_available() else 'cpu'

    # Gunicorn / production flag
    DEBUG = os.environ.get('FLASK_ENV', 'production') != 'production'
