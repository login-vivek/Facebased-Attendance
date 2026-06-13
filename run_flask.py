import os
import sys
import subprocess

def install_requirements():
    """Install required packages"""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("Requirements installed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"Error installing requirements: {e}")
        return False
    return True

def run_flask_app():
    """Run the Flask application"""
    try:
        from app import app
        print("Starting Flask Face Recognition API...")
        print("Available endpoints:")
        print("  POST /classroom/<id>/detect_faces - Detect faces in group photo")
        print("  POST /classroom/<id>/assign_roll_numbers - Assign roll numbers to faces")
        print("  POST /classroom/<id>/train_model - Train recognition model")
        print("  POST /classroom/<id>/recognize_faces - Take attendance")
        print("  GET  /classroom/<id>/status - Get classroom status")
        
        app.run(host='0.0.0.0', port=8000, debug=True)
    except ImportError as e:
        print(f"Import error: {e}")
        print("Please install the required packages first.")
        return False
    except Exception as e:
        print(f"Error starting Flask app: {e}")
        return False

if __name__ == '__main__':
    print("Face Recognition Flask API Setup")
    print("=" * 40)
    
    # Check if requirements.txt exists
    if not os.path.exists('requirements.txt'):
        print("requirements.txt not found!")
        sys.exit(1)
    
    # Install requirements
    print("Installing requirements...")
    if not install_requirements():
        sys.exit(1)
    
    # Run Flask app
    run_flask_app()