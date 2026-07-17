import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

# 1. Load keys locally from .env
load_dotenv()

app = Flask(__name__)

# 2. Grab your Database URL safely
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'local-dev-fallback')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True, "pool_recycle": 300}

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

@app.route('/api/users/search', methods=['GET'])
def search_users():
    query = request.args.get('query', '').strip()
    current_user_id = request.args.get('current_user_id') # Pass this from app to exclude self

    if not query:
        return jsonify([])

    # Use Postgres word_similarity or similarity index
    # Note: Requires 'pg_trgm' extension enabled in Postgres
    similarity = func.similarity(User.username, query)
    
    results = User.query.filter(User.username.ilike(f"%{query}%"))\
        .order_by(similarity.desc())\
        .limit(5)\
        .all()

    return jsonify([user.to_dict() for user in results])


@app.route('/api/chats/initiate', methods=['POST'])
def initiate_chat():
    data = request.get_json() or {}
    user_a_id = data.get('user_id_a') # The person initiating
    user_b_id = data.get('user_id_b') # The person being chatted with

    if not user_a_id or not user_b_id:
        return jsonify({"status": "error", "message": "Missing user IDs"}), 400

    # Check if a 1-on-1 room already exists between these two
    # This is a simplified check for 1-on-1 chats
    existing_room = db.session.query(ChatRoom).join(ChatParticipant)\
        .filter(ChatRoom.is_group == False)\
        .filter(ChatParticipant.user_id.in_([user_a_id, user_b_id]))\
        .group_by(ChatRoom.id)\
        .having(func.count(ChatParticipant.id) == 2)\
        .first()

    if existing_room:
        return jsonify({"status": "success", "chatId": existing_room.id}), 200

    # Create new room
    new_room = ChatRoom(is_group=False)
    db.session.add(new_room)
    db.session.flush() # Get the ID before commit

    # Add both participants
    p1 = ChatParticipant(user_id=user_a_id, room_id=new_room.id)
    p2 = ChatParticipant(user_id=user_b_id, room_id=new_room.id)
    db.session.add_all([p1, p2])
    db.session.commit()

    return jsonify({"status": "success", "chatId": new_room.id}), 201

# ... Keep your existing /register and /login routes ...
