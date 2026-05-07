import time
import json
import threading
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import mysql.connector
from mysql.connector import Error
import paho.mqtt.client as mqtt

app = Flask(__name__)
app.secret_key = 'super_secret_key_monitoring'  # Change this in production

# --- CONFIGURATION ---
DB_HOST = "localhost"
DB_USER = "root"
DB_PASS = ""
DB_NAME = "monitoring_server_room"

MQTT_BROKER = "192.168.1.16"
MQTT_PORT = 1883
MQTT_TOPIC = "220511203/monitoring/server/data"

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
            return User(id=user_record['id'], nama=user_record['nama'], email=user_record['email'], role=user_record['role'])
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
        
        # Save to database
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
        # Note: Event trigger logic can also be placed here if needed.
    except Exception as e:
        print(f"[MQTT] Error parsing message: {e}")

def mqtt_worker():
    # Paho mqtt v2.0+ requires CallbackAPIVersion
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "Flask_Backend_Monitor")
    client.on_connect = on_mqtt_connect
    client.on_message = on_mqtt_message
    
    while True:
        try:
            print(f"[MQTT] Attempting to connect to {MQTT_BROKER}...")
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_forever()
        except Exception as e:
            print(f"[MQTT] Connection lost or failed: {e}. Retrying in 5 seconds...")
            time.sleep(5)

# Start MQTT thread before handling requests (only in main process)
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
            
            # Since the user requested using existing DB, and dummy data uses plain text for password 'admin123'
            if user and user['password'] == password:
                user_obj = User(id=user['id'], nama=user['nama'], email=user['email'], role=user['role'])
                login_user(user_obj)
                return redirect(url_for('index'))
            else:
                flash('Email atau password salah!', 'danger')
        else:
            flash('Gagal mengambil data dari database.', 'danger')
            
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
        # JOIN with users to get the user who might have triggered or is assigned to event (if needed)
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

# --- API ROUTES FOR AJAX/CHART ---

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
            # Need to convert datetime to string
            latest['created_at'] = latest['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            return jsonify(latest)
    return jsonify({})

@app.route('/api/chart')
@login_required
def api_chart():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        # Fetch last 30 entries for the chart, reverse them so oldest to newest left to right
        query = "SELECT * FROM (SELECT * FROM monitoring_logs ORDER BY id DESC LIMIT 30) sub ORDER BY id ASC"
        cursor.execute(query)
        records = cursor.fetchall()
        cursor.close()
        conn.close()
        
        labels = []
        suhu = []
        watt = []
        amper = []
        
        for r in records:
            labels.append(r['created_at'].strftime('%H:%M'))
            suhu.append(r['suhu'])
            watt.append(r['daya_watt'])
            amper.append(r['arus_listrik'])
            
        return jsonify({
            'labels': labels,
            'suhu': suhu,
            'watt': watt,
            'amper': amper
        })
    return jsonify({})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)

