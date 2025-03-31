from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import pandas as pd
import os
from datetime import datetime
import hashlib
from werkzeug.utils import secure_filename
import shutil

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Ensure data directory exists
if not os.path.exists('data'):
    os.makedirs('data')

# Ensure uploads directory exists
UPLOAD_FOLDER = 'data/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Initialize messages CSV if it doesn't exist
MESSAGES_FILE = 'data/messages.csv'
if not os.path.exists(MESSAGES_FILE):
    pd.DataFrame(columns=['timestamp', 'username', 'message', 'type']).to_csv(MESSAGES_FILE, index=False)

# Initialize users CSV if it doesn't exist
USERS_FILE = 'data/users.csv'
if not os.path.exists(USERS_FILE):
    pd.DataFrame(columns=['username', 'password_hash']).to_csv(USERS_FILE, index=False)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_DATA_SIZE = 400 * 1024 * 1024  # 400MB in bytes

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_data_size():
    """Calculate total size of data directory in bytes"""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk('data'):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size

def clear_data():
    """Clear all messages and uploaded files while preserving user accounts"""
    try:
        # Clear messages CSV
        pd.DataFrame(columns=['timestamp', 'username', 'message', 'type']).to_csv(MESSAGES_FILE, index=False)
        
        # Clear uploads directory
        for filename in os.listdir(UPLOAD_FOLDER):
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f'Error deleting {file_path}: {e}')
                
        return True
    except Exception as e:
        print(f'Error clearing data: {e}')
        return False

def check_and_clear_data():
    """Check data size and clear if exceeds limit"""
    current_size = get_data_size()
    if current_size > MAX_DATA_SIZE:
        print(f'Data size ({current_size} bytes) exceeds limit ({MAX_DATA_SIZE} bytes). Clearing data...')
        if clear_data():
            print('Data cleared successfully')
        else:
            print('Failed to clear data')

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No JSON data received'}), 400
            
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        # Check if username already exists
        users = pd.read_csv(USERS_FILE)
        if username in users['username'].values:
            return jsonify({'error': 'Username already exists'}), 400
        
        # Add new user
        new_user = pd.DataFrame({
            'username': [username],
            'password_hash': [hash_password(password)]
        })
        
        users = pd.concat([users, new_user], ignore_index=True)
        users.to_csv(USERS_FILE, index=False)
        
        return jsonify({'status': 'success', 'message': 'User registered successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No JSON data received'}), 400
            
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        # Check user credentials
        users = pd.read_csv(USERS_FILE)
        user = users[users['username'] == username]
        
        if user.empty or user['password_hash'].values[0] != hash_password(password):
            return jsonify({'error': 'Invalid username or password'}), 401
        
        return jsonify({
            'status': 'success',
            'username': username
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_image():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
            
        file = request.files['file']
        username = request.form.get('username')
        
        if not username:
            return jsonify({'error': 'Username is required'}), 400
            
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
            
        if file and allowed_file(file.filename):
            # Check and clear data if needed
            check_and_clear_data()
            
            filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            
            # Add image message to messages CSV
            messages = pd.read_csv(MESSAGES_FILE)
            new_message = pd.DataFrame({
                'timestamp': [datetime.now().isoformat()],
                'username': [username],
                'message': [filename],
                'type': ['image']
            })
            
            messages = pd.concat([messages, new_message], ignore_index=True)
            messages.to_csv(MESSAGES_FILE, index=False)
            
            return jsonify({
                'status': 'success',
                'filename': filename
            })
            
        return jsonify({'error': 'File type not allowed'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/images/<filename>', methods=['GET'])
def get_image(filename):
    try:
        return send_file(os.path.join(UPLOAD_FOLDER, filename))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/messages', methods=['GET'])
def get_messages():
    try:
        messages = pd.read_csv(MESSAGES_FILE)
        # Ensure all messages have a type field
        messages['type'] = messages['type'].fillna('text')
        return jsonify(messages.to_dict('records'))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/messages', methods=['POST'])
def send_message():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data received'}), 400
            
        username = data.get('username')
        message = data.get('message')
        message_type = data.get('type', 'text')  # Default to 'text' if type is not provided
        
        if not username or not message:
            return jsonify({'error': 'Username and message are required'}), 400
        
        # Verify user exists
        users = pd.read_csv(USERS_FILE)
        if username not in users['username'].values:
            return jsonify({'error': 'User not found'}), 401
        
        # Check and clear data if needed
        check_and_clear_data()
        
        # Add new message
        new_message = pd.DataFrame({
            'timestamp': [datetime.now().isoformat()],
            'username': [username],
            'message': [message],
            'type': [message_type]
        })
        
        messages = pd.read_csv(MESSAGES_FILE)
        messages = pd.concat([messages, new_message], ignore_index=True)
        messages.to_csv(MESSAGES_FILE, index=False)
        
        return jsonify({'status': 'success', 'message': 'Message sent successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000) 