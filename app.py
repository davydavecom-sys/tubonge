import os
from flask import Flask
from dotenv import load_application_env  # Or simply load_dotenv()
from dotenv import load_dotenv

# Now call the correct function name to load your keys
load_dotenv()

app = Flask(__name__)

# The rest of your database configuration stays the same...
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'local-dev-fallback-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')


@app.route('/')
def home():
    return "Secure Database API is running!"

if __name__ == '__main__':
    # Dynamic port for environments like Railway
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
