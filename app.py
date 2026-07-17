import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

# 1. Load keys locally from .env (Safe fallback configuration)
load_dotenv()

app = Flask(__name__)

# 2. Grab your Database URL safely from Render Environment
database_url = os.environ.get('DATABASE_URL')

# Fix Dialect Flag: SQLAlchemy strictly requires 'postgresql://' instead of 'postgres://'
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'local-dev-fallback')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url

# Critical Neon Configurations: Recheck dead connections before executing queries
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,    # Checks if connection is alive; reconnects if Neon was asleep
    "pool_recycle": 300,      # Refreshes connections every 5 minutes
}

# Initialize the database extension
db = SQLAlchemy(app)

# ==========================================
# DATABASE MODELS
# ==========================================
class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    
    # Usernames must be unique, non-empty, and indexed for fast authentication lookups
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    
    # NEVER store plaintext passwords! We store a secure 256-character cryptographic hash.
    password_hash = db.Column(db.String(256), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Helper methods to handle secure password operations seamlessly
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        """Helper to format user data cleanly into JSON responses for an Android app"""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "created_at": self.created_at.isoformat()
        }

# Create database tables automatically if they don't exist yet in Neon
with app.app_context():
    db.create_all()
    print("Database tables synchronized and verified successfully!")


# ==========================================
# API ROUTES
# ==========================================

@app.route('/')
def home():
    return "Secure API Gateway is Live!", 200


@app.route('/db-test')
def test_db():
    try:
        # Executes a raw text query to test the handshake
        db.session.execute(db.text('SELECT 1')).scalar()
        return {"status": "success", "message": "Successfully connected to Neon Postgres!"}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    
    # Validation checks
    if 'username' not in data or 'email' not in data or 'password' not in data:
        return jsonify({"status": "error", "message": "Missing required fields: username, email, password"}), 400
        
    username = data['username'].strip()
    email = data['email'].strip().lower()
    password = data['password']

    if not username or not email or not password:
        return jsonify({"status": "error", "message": "Fields cannot be blank"}), 400

    # Check if user already exists
    if User.query.filter_by(username=username).first():
        return jsonify({"status": "error", "message": "Username is already taken"}), 400
        
    if User.query.filter_by(email=email).first():
        return jsonify({"status": "error", "message": "Email is already registered"}), 400

    # Create and commit new user record securely
    try:
        new_user = User(username=username, email=email)
        new_user.set_password(password)  # Hashes the password under the hood
        
        db.session.add(new_user)
        db.session.commit()
        
        return jsonify({
            "status": "success",
            "message": "User account created successfully!",
            "user": new_user.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Database insertion failed: {str(e)}"}), 500


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    
    username_or_email = data.get('username') or data.get('email')
    password = data.get('password')

    if not username_or_email or not password:
        return jsonify({"status": "error", "message": "Missing identifier or password"}), 400

    # Support login using either the unique username or email handle
    user = User.query.filter((User.username == username_or_email) | (User.email == username_or_email.lower())).first()

    # Secure verification verification step
    if user and user.check_password(password):
        return jsonify({
            "status": "success",
            "message": "Login successful!",
            "user": user.to_dict()
        }), 200
        
    return jsonify({"status": "error", "message": "Invalid username, email, or password"}), 401


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
