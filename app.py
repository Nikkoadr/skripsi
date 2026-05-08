import time
import json
import threading
import os
import requests
import uuid

from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify
)

from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user
)

import mysql.connector
from mysql.connector import Error
import paho.mqtt.client as mqtt

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')
APP_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
APP_PORT = int(
    os.getenv('FLASK_PORT', 5000)
)

DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
DB_NAME = os.getenv('DB_NAME')

MQTT_BROKER = os.getenv('MQTT_BROKER')
MQTT_PORT = int(
    os.getenv('MQTT_PORT', 1883)
)

MQTT_USERNAME = os.getenv('MQTT_USERNAME')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD')
MQTT_TOPIC = os.getenv('MQTT_TOPIC')

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Ambang Batas (Thresholds)
SUHU_ATAS = 30.0
SUHU_BAWAH = 18.0
LEMBAB_ATAS = 70.0
LEMBAB_BAWAH = 30.0
WATT_ATAS = 3500.0
AMPER_BAWAH = 1.0
DURASI_MAKS_PINTU = 300  # detik (5 menit)
DURASI_MAKS_ARUS_MATI = 300  # detik (5 menit)

class AlertState:
    suhu_tinggi = False
    suhu_rendah = False
    lembab_tinggi = False
    lembab_rendah = False
    daya_overload = False
    arus_mati = False
    waktu_arus_mati = 0
    pintu_terbuka = False
    waktu_buka_pintu = 0
    alarm_pintu_sent = False

alert_state = AlertState()

def send_telegram_msg(pesan):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"Notifikasi IoT (Server) : \n{pesan}",
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[TELEGRAM] Error: {e}")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
class User(UserMixin):
    def __init__(self, id, nama, email):
        self.id = id
        self.nama = nama
        self.email = email

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
        print(f"[DATABASE] Error -> {e}")
        return None

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM users WHERE id = %s",
            (user_id,)
        )
        user_record = cursor.fetchone()
        cursor.close()
        conn.close()
        if user_record:
            return User(
                id=user_record['id'],
                nama=user_record['nama'],
                email=user_record['email']
            )
    return None

def on_mqtt_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print(
            f"[MQTT] Connected -> "
            f"{MQTT_BROKER}:{MQTT_PORT}"
        )
        client.subscribe(MQTT_TOPIC)
        print(
            f"[MQTT] Subscribe -> "
            f"{MQTT_TOPIC}"
        )
    else:
        print(
            f"[MQTT] Failed Connect -> "
            f"{reason_code}"
        )
def on_mqtt_disconnect(
    client,
    userdata,
    disconnect_flags,
    reason_code,
    properties=None
):
    print("[MQTT] Disconnected")
    
def log_event(event_type, deskripsi, status="INFO"):
    """Mencatat kejadian mentah ke tabel event_logs"""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Kita hanya fokus pada kolom utama sesuai request Anda
            query = """
                INSERT INTO event_logs (event_type, deskripsi, status) 
                VALUES (%s, %s, %s)
            """
            cursor.execute(query, (event_type, deskripsi, status))
            conn.commit()
            print(f"[EVENT-DB] {event_type} berhasil dicatat.")
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[EVENT-DB] Gagal mencatat: {e}")

def on_mqtt_message(client, userdata, msg):
    try:
        # 1. Parsing Data dari MQTT
        data = json.loads(msg.payload.decode('utf-8'))
        suhu = data.get('suhu', 0)
        lembab = data.get('lembab', 0)
        amper = data.get('amper', 0)
        watt = data.get('watt', 0)
        pintu = data.get('pintu', '-')
        
        print(f"[DATA] Suhu={suhu}°C | Lembab={lembab}% | Arus={amper}A | Daya={watt}W | Pintu={pintu}")
        
        # --- LOGIKA AMBANG BATAS, TELEGRAM & EVENT LOGS (STATUS BASED) ---
        
        # 1. Logika Suhu Atas (Overheat)
        if suhu > SUHU_ATAS and not alert_state.suhu_tinggi:
            msg_text = f"🔥 Panas (Overheat): {suhu:.1f}°C"
            send_telegram_msg(msg_text)
            log_event("Suhu", msg_text, status="OVERHEAT")
            alert_state.suhu_tinggi = True
        elif suhu <= SUHU_ATAS and alert_state.suhu_tinggi:
            msg_text = f"✅ Suhu Kembali Normal: {suhu:.1f}°C"
            send_telegram_msg(msg_text)
            log_event("Suhu", msg_text, status="NORMAL")
            alert_state.suhu_tinggi = False
            
        # 2. Logika Suhu Bawah (Terlalu Dingin)
        if suhu < SUHU_BAWAH and not alert_state.suhu_rendah:
            msg_text = f"❄️ Dingin: {suhu:.1f}°C"
            send_telegram_msg(msg_text)
            log_event("Suhu", msg_text, status="COLD")
            alert_state.suhu_rendah = True
        elif suhu >= SUHU_BAWAH and alert_state.suhu_rendah:
            msg_text = f"✅ Suhu Dingin Berakhir: {suhu:.1f}°C"
            send_telegram_msg(msg_text)
            log_event("Suhu", msg_text, status="NORMAL")
            alert_state.suhu_rendah = False
            
        # 3. Logika Kelembapan Atas
        if lembab > LEMBAB_ATAS and not alert_state.lembab_tinggi:
            msg_text = f"💦 Terlalu Lembab: {lembab:.0f}%"
            send_telegram_msg(msg_text)
            log_event("Humidity", msg_text, status="HIGH")
            alert_state.lembab_tinggi = True
        elif lembab <= LEMBAB_ATAS and alert_state.lembab_tinggi:
            msg_text = f"✅ Kelembapan Normal: {lembab:.0f}%"
            send_telegram_msg(msg_text)
            log_event("Humidity", msg_text, status="NORMAL")
            alert_state.lembab_tinggi = False

        # 4. Logika Listrik & Shutdown
        if amper < AMPER_BAWAH:
            if not alert_state.arus_mati:
                msg_text = f"🚨 ALARM: LISTRIK MATI!\nArus: {amper:.2f}A\nServer akan otomatis shutdown dalam 5 menit."
                send_telegram_msg(msg_text)
                log_event("Listrik", msg_text, status="OFF") # Catat Titik Mati
                alert_state.arus_mati = True
                alert_state.waktu_arus_mati = time.time()
                alert_state.daya_overload = False
            else:
                # Timer Shutdown Otomatis
                if alert_state.waktu_arus_mati > 0 and (time.time() - alert_state.waktu_arus_mati >= DURASI_MAKS_ARUS_MATI):
                    msg_shutdown = "⚠️ Waktu UPS habis. Melakukan SHUTDOWN SERVER otomatis!"
                    send_telegram_msg(msg_shutdown)
                    log_event("Sistem", msg_shutdown, status="SHUTDOWN")
                    
                    print("[SYSTEM] Executing OS Shutdown...")
                    alert_state.waktu_arus_mati = 0 
                    if os.name == 'nt':
                        os.system("shutdown /s /t 10")
                    else:
                        os.system("sudo shutdown -h now")

        elif watt > WATT_ATAS:
            if not alert_state.daya_overload:
                msg_text = f"⚡ OVERLOAD DAYA!\nArus: {amper:.2f}A\nDaya: {watt:.0f}W"
                send_telegram_msg(msg_text)
                log_event("Listrik", msg_text, status="OVERLOAD")
                alert_state.daya_overload = True
                alert_state.arus_mati = False
                alert_state.waktu_arus_mati = 0
        
        elif amper >= AMPER_BAWAH:
            if alert_state.arus_mati or alert_state.daya_overload:
                msg_text = f"✅ LISTRIK NORMAL:\nArus: {amper:.2f}A\nDaya: {watt:.0f}W\nShutdown otomatis dibatalkan."
                send_telegram_msg(msg_text)
                log_event("Listrik", msg_text, status="ON") # Catat Titik Nyala
                alert_state.arus_mati = False
                alert_state.waktu_arus_mati = 0
                alert_state.daya_overload = False

        # 5. Logika Pintu
        is_pintu_terbuka = (pintu == 'terbuka')
        if is_pintu_terbuka != alert_state.pintu_terbuka:
            alert_state.pintu_terbuka = is_pintu_terbuka
            if is_pintu_terbuka:
                status_msg = "🚪 PINTU DIBUKA!"
                send_telegram_msg(status_msg)
                log_event("Keamanan", status_msg, status="OPEN") # Catat Titik Buka
                alert_state.waktu_buka_pintu = time.time()
            else:
                status_msg = "🚪 Pintu Ditutup."
                send_telegram_msg(status_msg)
                log_event("Keamanan", status_msg, status="CLOSED") # Catat Titik Tutup
                alert_state.alarm_pintu_sent = False
                
        # Peringatan Pintu Terbuka Terlalu Lama
        if alert_state.pintu_terbuka:
            if time.time() - alert_state.waktu_buka_pintu >= DURASI_MAKS_PINTU:
                if not alert_state.alarm_pintu_sent:
                    msg_pintu_lama = "🚨 ALERT: Pintu Terbuka > 5 Menit!"
                    send_telegram_msg(msg_pintu_lama)
                    log_event("Keamanan", msg_pintu_lama, status="WARNING")
                    alert_state.alarm_pintu_sent = True

        # --- SIMPAN DATA RUTIN KE MONITORING_LOGS ---
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            query = """
                INSERT INTO monitoring_logs 
                (suhu, kelembapan, arus_listrik, daya_watt, status_pintu, power_status)
                VALUES (%s,%s,%s,%s,%s,%s)
            """
            power_status = 'off' if amper < AMPER_BAWAH else 'on'
            values = (
                float(suhu), float(lembab), float(amper),
                float(watt), str(pintu), power_status
            )
            cursor.execute(query, values)
            conn.commit()
            cursor.close()
            conn.close()
            print("[DATABASE] Periodic log saved.")

    except Exception as e:
        print(f"[ERROR on_mqtt_message] {e}")

def mqtt_worker():
    client_id = f"Flask_Monitor_{uuid.uuid4().hex[:8]}"
    print(f"[MQTT] Worker Started with ID: {client_id}")
    
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id,
        clean_session=True
    )

    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    client.on_connect = on_mqtt_connect
    client.on_disconnect = on_mqtt_disconnect
    client.on_message = on_mqtt_message
    client.reconnect_delay_set(min_delay=1, max_delay=120)

    try:
        client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=30)
        client.loop_start()

        while True:
            time.sleep(1)
            
    except Exception as e:
        print(f"[MQTT] Fatal Error in Worker: {e}")
    finally:
        client.loop_stop()
        print("[MQTT] Worker Stopped")

mqtt_thread = threading.Thread(target=mqtt_worker, daemon=True)
mqtt_thread.start()

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
            cursor.execute(
                "SELECT * FROM users WHERE email = %s",
                (email,)
            )
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            if user and (check_password_hash(user['password'], password) or user['password'] == password):
                user_obj = User(
                    id=user['id'],
                    nama=user['nama'],
                    email=user['email']
                )
                login_user(user_obj)
                return redirect(url_for('index'))
            else:
                flash(
                    'Email atau password salah!',
                    'danger'
                )
        else:
            flash(
                'Database gagal terhubung!',
                'danger'
            )
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
        cursor.execute("""
            SELECT *
            FROM monitoring_logs
            ORDER BY created_at DESC
            LIMIT 1000
        """)
        logs_data = cursor.fetchall()
        cursor.close()
        conn.close()
    return render_template(
        'logs.html',
        logs=logs_data
    )
@app.route('/events')

@login_required
def events():
    conn = get_db_connection()
    events_data = []
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT 
                    id, 
                    event_type, 
                    deskripsi, 
                    status, 
                    created_at 
                FROM event_logs 
                ORDER BY created_at DESC
            """
            cursor.execute(query)
            events_data = cursor.fetchall()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Error fetching events: {e}")
            
    return render_template(
        'events.html',
        events=events_data
    )
@app.route('/api/latest')

@login_required
def api_latest():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT *
            FROM monitoring_logs
            ORDER BY id DESC
            LIMIT 1
        """)
        latest = cursor.fetchone()
        cursor.close()
        conn.close()
        if latest:
            latest['created_at'] = latest[
                'created_at'
            ].strftime('%Y-%m-%d %H:%M:%S')
            return jsonify(latest)
    return jsonify({})
@app.route('/api/chart')

@login_required
def api_chart():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT *
            FROM (
                SELECT *
                FROM monitoring_logs
                ORDER BY id DESC
                LIMIT 30
            ) sub
            ORDER BY id ASC
        """
        cursor.execute(query)
        records = cursor.fetchall()
        cursor.close()
        conn.close()
        data = {
            'labels': [
                r['created_at'].strftime('%H:%M')
                for r in records
            ],
            'suhu': [
                r['suhu']
                for r in records
            ],
            'watt': [
                r['daya_watt']
                for r in records
            ],
            'amper': [
                r['arus_listrik']
                for r in records
            ]
        }
        return jsonify(data)

    return jsonify({})

if __name__ == '__main__':

    print(
        f"[FLASK] Running -> "
        f"{APP_HOST}:{APP_PORT}"
    )
    test_db = get_db_connection()
    if test_db:
        print("[DATABASE] Connected")
        test_db.close()
    else:
        print("[DATABASE] Failed")
    app.run(
        debug=True,
        host=APP_HOST,
        port=APP_PORT,
        use_reloader=False
    )
