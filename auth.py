import os
import sqlite3
import hashlib
import secrets
import jwt
import datetime
from functools import wraps
from flask import request, jsonify
from config import Config

DB_PATH = os.path.join(Config.BASE_DIR, 'users.db')

# ── DB setup ──────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT    UNIQUE NOT NULL,
            email    TEXT    UNIQUE NOT NULL,
            password TEXT    NOT NULL,
            salt     TEXT    NOT NULL,
            created  TEXT    NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return hashed, salt

# ── User ops ──────────────────────────────────────────────────────────────────

def create_user(username, email, password):
    hashed, salt = hash_password(password)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            'INSERT INTO users (username, email, password, salt, created) VALUES (?, ?, ?, ?, ?)',
            (username.strip(), email.strip().lower(), hashed, salt,
             datetime.datetime.utcnow().isoformat())
        )
        conn.commit()
        return True, "User created successfully."
    except sqlite3.IntegrityError as e:
        if 'username' in str(e):
            return False, "Username already taken."
        return False, "Email already registered."
    finally:
        conn.close()

def verify_user(username, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, username, email, password, salt FROM users WHERE username = ?',
              (username.strip(),))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    uid, uname, email, stored_hash, salt = row
    hashed, _ = hash_password(password, salt)
    if hashed == stored_hash:
        return {'id': uid, 'username': uname, 'email': email}
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
            # Also check cookie for browser requests
            token = request.cookies.get('token')
        if not token:
            return jsonify({'error': 'Authentication required.'}), 401
        payload = decode_token(token)
        if not payload:
            return jsonify({'error': 'Invalid or expired token. Please log in again.'}), 401
        request.current_user = payload
        return f(*args, **kwargs)
    return decorated
