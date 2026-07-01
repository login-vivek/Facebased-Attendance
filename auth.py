import os
import hashlib
import secrets
import jwt
import datetime
from functools import wraps
from flask import request, jsonify
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from config import Config

# ── MongoDB connection ────────────────────────────────────────────────────────

_client = None
_db = None

def get_db():
    global _client, _db
    if _db is None:
        mongo_uri = os.environ.get('MONGO_URI')
        if not mongo_uri:
            raise RuntimeError('MONGO_URI environment variable is not set.')
        _client = MongoClient(mongo_uri)
        _db = _client['attendance_db']
        # Unique indexes
        _db.users.create_index('username', unique=True)
        _db.users.create_index('email', unique=True)
    return _db

def init_db():
    """Call on app startup to ensure indexes exist."""
    try:
        get_db()
        print('MongoDB connected successfully.')
    except Exception as e:
        print(f'Warning: MongoDB connection failed: {e}')

# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return hashed, salt

# ── User ops ──────────────────────────────────────────────────────────────────

def create_user(username, email, password):
    db = get_db()
    hashed, salt = hash_password(password)
    try:
        db.users.insert_one({
            'username': username.strip(),
            'email':    email.strip().lower(),
            'password': hashed,
            'salt':     salt,
            'created':  datetime.datetime.utcnow()
        })
        return True, 'User created successfully.'
    except DuplicateKeyError as e:
        if 'username' in str(e):
            return False, 'Username already taken.'
        return False, 'Email already registered.'
    except Exception as e:
        return False, f'Database error: {str(e)}'

def verify_user(username, password):
    db = get_db()
    user = db.users.find_one({'username': username.strip()})
    if not user:
        return None
    hashed, _ = hash_password(password, user['salt'])
    if hashed == user['password']:
        return {
            'id':       str(user['_id']),
            'username': user['username'],
            'email':    user['email']
        }
    return None

# ── JWT helpers ───────────────────────────────────────────────────────────────

def generate_token(user):
    payload = {
        'user_id':  user['id'],
        'username': user['username'],
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=12)
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm='HS256')

def decode_token(token):
    try:
        return jwt.decode(token, Config.SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# ── Auth decorator ────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1]
        if not token:
            token = request.cookies.get('token')
        if not token:
            return jsonify({'error': 'Authentication required.'}), 401
        payload = decode_token(token)
        if not payload:
            return jsonify({'error': 'Invalid or expired token. Please log in again.'}), 401
        request.current_user = payload
        return f(*args, **kwargs)
    return decorated
