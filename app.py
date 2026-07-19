import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

# 1. Load keys locally from .env
load_dotenv()

app = Flask(__name__)
CORS(app) # 🚀 Crucial: Allows your mobile app to communicate with Render securely

# 2. Grab your Database URL safely
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

# Ensure query parameters force SSL mode for safe Neon cloud hosting
if database_url and "sslmode=" not in database_url:
    database_url += "&sslmode=require" if "?" in database_url else "?sslmode=require"

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'local-dev-fallback')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True, "pool_recycle": 300}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================================
# DATABASE MODELS
# ==========================================

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {"id": self.id, "username": self.username, "email": self.email}


class ChatRoom(db.Model):
    __tablename__ = 'chat_rooms'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True)
    is_group = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Participants in this room
    participants = db.relationship('ChatParticipant', backref='room', lazy='dynamic')
    messages = db.relationship('Message', backref='room', lazy='dynamic')

class ChatParticipant(db.Model):
    __tablename__ = 'chat_participants'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('chat_rooms.id', ondelete='CASCADE'), nullable=False)

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('chat_rooms.id', ondelete='CASCADE'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

# Create tables
with app.app_context():
    # Enable pg_trgm for similarity search
    try:
        db.session.execute(db.text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
        db.session.commit()
    except:
        db.session.rollback()
    db.create_all()

# ==========================================
# API ROUTES
# ==========================================

# 🌍 Base/Root Status Route (Let's you check if the site is up using a browser)
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
        data = request.get_json() or {}
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')

        if not username or not email or not password:
            return jsonify({"status": "error", "message": "All fields are required"}), 400

        if User.query.filter_by(username=username).first():
            return jsonify({"status": "error", "message": "Username is already taken"}), 400
            
        if User.query.filter_by(email=email).first():
            return jsonify({"status": "error", "message": "Email already registered"}), 400

        new_user = User(username=username, email=email)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Account created successfully!",
            "user": new_user.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Server database error: {str(e)}"}), 500


# 🔑 Authentication Login Endpoint
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip()
        password = data.get('password', '')

        if not email or not password:
            return jsonify({"status": "error", "message": "Email and password are required"}), 400

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            return jsonify({
                "status": "success",
                "message": "Welcome back!",
                "user": user.to_dict()
            }), 200
        else:
            return jsonify({"status": "error", "message": "Invalid email or password credentials"}), 401

    except Exception as e:
        return jsonify({"status": "error", "message": f"Server processing error: {str(e)}"}), 500


@app.route('/api/users/search', methods=['GET'])
def search_users():
    query = request.args.get('query', '').strip()
    current_user_id = request.args.get('current_user_id')

    if not query:
        return jsonify([])

    similarity = func.similarity(User.username, query)
    
    # Exclude self if current_user_id is passed
    base_query = User.query.filter(User.username.ilike(f"%{query}%"))
    if current_user_id:
        base_query = base_query.filter(User.id != int(current_user_id))

    results = base_query.order_by(similarity.desc()).limit(5).all()
    return jsonify([user.to_dict() for user in results])


@app.route('/api/chats/initiate', methods=['POST'])
def initiate_chat():
    data = request.get_json() or {}
    user_a_id = data.get('user_id_a') 
    user_b_id = data.get('user_id_b') 

    if not user_a_id or not user_b_id:
        return jsonify({"status": "error", "message": "Missing user IDs"}), 400

    existing_room = db.session.query(ChatRoom).join(ChatParticipant)\
        .filter(ChatRoom.is_group == False)\
        .filter(ChatParticipant.user_id.in_([user_a_id, user_b_id]))\
        .group_by(ChatRoom.id)\
        .having(func.count(ChatParticipant.id) == 2)\
        .first()

    if existing_room:
        return jsonify({"status": "success", "chatId": existing_room.id}), 200

    new_room = ChatRoom(is_group=False)
    db.session.add(new_room)
    db.session.flush() 

    p1 = ChatParticipant(user_id=user_a_id, room_id=new_room.id)
    p2 = ChatParticipant(user_id=user_b_id, room_id=new_room.id)
    db.session.add_all([p1, p2])
    db.session.commit()

    return jsonify({"status": "success", "chatId": new_room.id}), 201

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
