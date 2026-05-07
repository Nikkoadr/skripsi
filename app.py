import time
import json
import threading
import os
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import mysql.connector
from mysql.connector import Error
import paho.mqtt.client as mqtt

# Memuat variabel dari file .env
load_dotenv()

app = Flask(__name__)

# --- CONFIGURATION DARI .ENV ---
# Flask
app.secret_key = os.getenv('FLASK_SECRET_KEY')
APP_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
APP_PORT = int(os.getenv('FLASK_PORT', 5000))

# Database
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS', '')
DB_NAME = os.getenv('DB_NAME')

# MQTT
MQTT_BROKER = os.getenv('MQTT_BROKER')
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
MQTT_USERNAME = os.getenv('MQTT_USERNAME')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD')
MQTT_TOPIC = os.getenv('MQTT_TOPIC')

# Setup Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, nama, email, role):
        self.id = id
        self.nama = nama
        self.email = email
        self.role = role

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME
        )
        return conn
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user_record = cursor.fetchone()
        cursor.close()
        conn.close()
        if user_record:
            return User(id=user_record['id'], nama=user_record['nama'], 
                        email=user_record['email'], role=user_record['role'])
    return None

# --- MQTT BACKGROUND THREAD ---
def on_mqtt_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0 or reason_code == "Success":
        print(f"[MQTT] Connected to {MQTT_BROKER}")
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"[MQTT] Failed to connect, return code {reason_code}")

def on_mqtt_message(client, userdata, msg):
    try:
        payload = msg.payload.decode('utf-8')
        data = json.loads(payload)
        
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            query = """INSERT INTO monitoring_logs 
                       (suhu, kelembapan, arus_listrik, daya_watt, status_pintu, power_status) 
                       VALUES (%s, %s, %s, %s, %s, %s)"""
            values = (
                data.get('suhu', 0.0),
                data.get('lembab', 0.0),
                data.get('amper', 0.0),
                data.get('watt', 0.0),
                data.get('pintu', 'tertutup'),
                data.get('power_status', 'on')
            )
            cursor.execute(query, values)
            conn.commit()
            cursor.close()
            conn.close()
    except Exception as e:
        print(f"[MQTT] Error processing message: {e}")

def mqtt_worker():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "Flask_Backend_Monitor")
    
    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        
    client.on_connect = on_mqtt_connect
    client.on_message = on_mqtt_message
    
    while True:
        try:
            print(f"[MQTT] Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_forever()
        except Exception as e:
            print(f"[MQTT] Connection lost: {e}. Retrying in 5 seconds...")
            time.sleep(5)

# Start MQTT thread
mqtt_thread = threading.Thread(target=mqtt_worker, daemon=True)
mqtt_thread.start()

# --- ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if user and user['password'] == password:
                user_obj = User(id=user['id'], nama=user['nama'], 
                                email=user['email'], role=user['role'])
                login_user(user_obj)
                return redirect(url_for('index'))
            else:
                flash('Email atau password salah!', 'danger')
        else:
            flash('Gagal terhubung ke database.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/logs')
@login_required
def logs():
    conn = get_db_connection()
    logs_data = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM monitoring_logs ORDER BY created_at DESC LIMIT 1000")
        logs_data = cursor.fetchall()
        cursor.close()
        conn.close()
    return render_template('logs.html', logs=logs_data)

@app.route('/events')
@login_required
def events():
    conn = get_db_connection()
    events_data = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT e.*, u.nama as nama_user 
            FROM event_logs e 
            LEFT JOIN users u ON e.user_id = u.id 
            ORDER BY e.created_at DESC
        """
        cursor.execute(query)
        events_data = cursor.fetchall()
        cursor.close()
        conn.close()
    return render_template('events.html', events=events_data)

@app.route('/api/latest')
@login_required
def api_latest():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM monitoring_logs ORDER BY id DESC LIMIT 1")
        latest = cursor.fetchone()
        cursor.close()
        conn.close()
        if latest:
            latest['created_at'] = latest['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            return jsonify(latest)
    return jsonify({})

@app.route('/api/chart')
@login_required
def api_chart():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        query = "SELECT * FROM (SELECT * FROM monitoring_logs ORDER BY id DESC LIMIT 30) sub ORDER BY id ASC"
        cursor.execute(query)
        records = cursor.fetchall()
        cursor.close()
        conn.close()
        
        data = {
            'labels': [r['created_at'].strftime('%H:%M') for r in records],
            'suhu': [r['suhu'] for r in records],
            'watt': [r['daya_watt'] for r in records],
            'amper': [r['arus_listrik'] for r in records]
        }
        return jsonify(data)
    return jsonify({})

if __name__ == '__main__':
    app.run(
        debug=True, 
        host=APP_HOST, 
        port=APP_PORT, 
        use_reloader=False
    )