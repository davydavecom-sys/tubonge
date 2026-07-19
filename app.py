import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()
app = Flask(__name__)
CORS(app)

# Database Setup
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'local-dev-fallback')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Models ---
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def to_dict(self):
        return {"id": self.id, "username": self.username, "email": self.email}

class ChatRoom(db.Model):
    __tablename__ = 'chat_rooms'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True)
    is_group = db.Column(db.Boolean, default=False)
    participants = db.relationship('ChatParticipant', backref='room', lazy='dynamic')
    messages = db.relationship('Message', backref='room', lazy='dynamic')

class ChatParticipant(db.Model):
    __tablename__ = 'chat_participants'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('chat_rooms.id', ondelete='CASCADE'), nullable=False)
    user = db.relationship('User', backref='memberships')

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('chat_rooms.id', ondelete='CASCADE'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sender = db.relationship('User', backref='sent_messages')

    def to_dict(self):
        return {
            "id": self.id,
            "room_id": self.room_id,
            "sender_id": self.sender_id,
            "sender_name": self.sender.username,
            "content": self.content,
            "timestamp": self.timestamp.strftime("%H:%M")
        }

# Ensure Room 1 exists
with app.app_context():
    db.create_all()
    if not ChatRoom.query.get(1):
        db.session.add(ChatRoom(id=1, name="Tubonge Updates", is_group=True))
        db.session.commit()

# --- Routes ---
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data['email']).first()
    if user and check_password_hash(user.password_hash, data['password']):
        # Auto-join updates room
        if not ChatParticipant.query.filter_by(user_id=user.id, room_id=1).first():
            db.session.add(ChatParticipant(user_id=user.id, room_id=1))
            db.session.commit()
        return jsonify({"status": "success", "user": user.to_dict()})
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401

@app.route('/api/chats/user_chats', methods=['GET'])
def get_user_chats():
    uid = request.args.get('user_id', type=int)
    # Find all rooms where the user is a participant
    memberships = ChatParticipant.query.filter_by(user_id=uid).all()
    results = []
    for m in memberships:
        room = m.room
        if room.is_group:
            name = room.name or "Group"
        else:
            other = ChatParticipant.query.filter(ChatParticipant.room_id == room.id, ChatParticipant.user_id != uid).first()
            name = other.user.username if other else "Private Chat"
        
        last = room.messages.order_by(Message.timestamp.desc()).first()
        results.append({
            "id": room.id,
            "display_name": name,
            "last_message": last.content if last else "No messages yet",
            "timestamp": last.timestamp.strftime("%H:%M") if last else None
        })
    return jsonify(results)

# [Include existing /register, /search, /initiate, /messages, /send routes]
