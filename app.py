import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()
app = Flask(__name__)
CORS(app)

# Database Configuration
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

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
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    def to_dict(self):
        return {"id": self.id, "username": self.username, "email": self.email}

class ChatRoom(db.Model):
    __tablename__ = 'chat_rooms'
    id = db.Column(db.Integer, primary_key=True)
    is_group = db.Column(db.Boolean, default=False)
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
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    sender = db.relationship('User', backref='messages')

    def to_dict(self):
        return {
            "id": self.id,
            "room_id": self.room_id,
            "sender_id": self.sender_id,
            "sender_name": self.sender.username,
            "content": self.content,
            "timestamp": self.timestamp.strftime("%H:%M") # Appears as "10:30"
        }

# ==========================================
# API ROUTES
# ==========================================

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    new_user = User(username=data['username'], email=data['email'])
    new_user.set_password(data['password'])
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"status": "success", "user": new_user.to_dict()}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data['email']).first()
    if user and user.check_password(data['password']):
        return jsonify({"status": "success", "user": user.to_dict()}), 200
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401

@app.route('/api/users/search', methods=['GET'])
def search_users():
    query = request.args.get('query', '')
    similarity = func.similarity(User.username, query)
    results = User.query.filter(User.username.ilike(f"%{query}%")).order_by(similarity.desc()).limit(5).all()
    return jsonify([user.to_dict() for user in results])

@app.route('/api/chats/initiate', methods=['POST'])
def initiate_chat():
    data = request.get_json()
    u1, u2 = data['user_id_a'], data['user_id_b']
    # Check for existing 1-on-1
    room = db.session.query(ChatRoom).join(ChatParticipant).filter(ChatRoom.is_group == False)\
        .filter(ChatParticipant.user_id.in_([u1, u2])).group_by(ChatRoom.id).having(func.count(ChatParticipant.id) == 2).first()
    if room:
        return jsonify({"status": "success", "chatId": room.id})
    new_room = ChatRoom(is_group=False)
    db.session.add(new_room)
    db.session.flush()
    db.session.add_all([ChatParticipant(user_id=u1, room_id=new_room.id), ChatParticipant(user_id=u2, room_id=new_room.id)])
    db.session.commit()
    return jsonify({"status": "success", "chatId": new_room.id}), 201

@app.route('/api/chats/messages', methods=['GET'])
def get_messages():
    room_id = request.args.get('room_id')
    messages = Message.query.filter_by(room_id=room_id).order_by(Message.timestamp.asc()).all()
    return jsonify([m.to_dict() for m in messages])

@app.route('/api/chats/send', methods=['POST'])
def send_message():
    data = request.get_json()
    msg = Message(room_id=data['room_id'], sender_id=data['sender_id'], content=data['content'])
    db.session.add(msg)
    db.session.commit()
    return jsonify({"status": "success"}), 201

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
