import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

# Load keys locally from .env
load_dotenv()

app = Flask(__name__)

# 1. Grab your Database URL safely
database_url = os.environ.get('DATABASE_URL')

# 2. Fix Dialect Flag: SQLAlchemy strictly requires 'postgresql://' instead of 'postgres://'
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'local-dev-fallback')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url

# 3. Critical Neon Configurations: Recheck dead connections before executing queries
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,    # Checks if connection is alive; reconnects if Neon was asleep
    "pool_recycle": 300,      # Refreshes connections every 5 minutes
}

# Initialize the database extension
db = SQLAlchemy(app)

# Quick testing route to see if database queries resolve
@app.route('/db-test')
def test_db():
    try:
        # Executes a raw text query to test the handshake
        db.session.execute(db.text('SELECT 1')).scalar()
        return {"status": "success", "message": "Successfully connected to Neon Postgres!"}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
