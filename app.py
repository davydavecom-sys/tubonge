import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
CORS(app)

# 🔐 Security Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'tubonge_fallback_secret_key_2026')

# 🔌 Database Configuration (Neon Postgres Connection Setup)
db_url = os.environ.get('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    # Fixes a common compatibility issue where older tools inject postgres:// instead of postgresql://
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# Ensure query parameters force SSL authentication mode for secure cloud transactions
if db_url and "sslmode=" not in db_url:
    if "?" in db_url:
        db_url += "&sslmode=require"
    else:
        db_url += "?sslmode=require"

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# 💾 Database Models
class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "created_at": self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

# 🌍 Base/Root Status Health Route (Solves the browser 404 mystery)
@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "status": "healthy",
        "message": "Tubonge API Backend is active and running!",
        "timestamp": datetime.utcnow().isoformat()
    }), 200

# 🚀 Registration Endpoint
@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "Missing JSON request body"}), 400

        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')

        if not username or not email or not password:
            return jsonify({"status": "error", "message": "All input fields are required"}), 400

        # Check if user details conflict with existing accounts
        if User.query.filter_by(username=username).first():
            return jsonify({"status": "error", "message": "Username is already taken"}), 400
            
        if User.query.filter_by(email=email).first():
            return jsonify({"status": "error", "message": "An account with this email already exists"}), 400

        # Safe password encryption transformation
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, email=email, password_hash=hashed_password)

        db.session.add(new_user)
        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Account created successfully!",
            "user": new_user.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Server transaction error: {str(e)}"}), 500

# 🔑 Authentication Login Endpoint
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "Missing JSON request body"}), 400

        email = data.get('email', '').strip()
        password = data.get('password', '')

        if not email or not password:
            return jsonify({"status": "error", "message": "Email and password are required"}), 400

        # Look up records matching criteria
        user = User.query.filter_by(email=email).first()

        # Secure check matching the payload against the cryptographically stored hash
        if user and check_password_hash(user.password_hash, password):
            return jsonify({
                "status": "success",
                "message": "Welcome back!",
                "user": user.to_dict()
            }), 200
        else:
            return jsonify({"status": "error", "message": "Invalid email or password credentials"}), 401

    except Exception as e:
        return jsonify({"status": "error", "message": f"Server execution error: {str(e)}"}), 500

# 🔄 System Hook: Automatically creates missing database tables safely on boot
with app.app_context():
    try:
        db.create_all()
        print("Database verification passed: Tables initialized cleanly.")
    except Exception as err:
        print(f"Critical error initializing database tables on boot: {err}")

if __name__ == '__main__':
    # Binds server configurations dynamically based on container environments
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
