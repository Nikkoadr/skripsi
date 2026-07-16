import time
import json
import threading
import os
import requests
import uuid

from dotenv import load_dotenv
from werkzeug.security import check_password_hash

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

app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not app.secret_key:
    raise ValueError("FLASK_SECRET_KEY belum diatur pada file .env")

APP_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("FLASK_PORT", 5000))

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")

MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_TOPIC = os.getenv("MQTT_TOPIC")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

_settings_cache = {}
_settings_cache_time = 0
CACHE_TTL = 60

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

def load_settings():
    """Muat seluruh pengaturan dari database ke cache."""
    global _settings_cache, _settings_cache_time
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT setting_key, setting_value FROM app_settings")
        rows = cursor.fetchall()
        _settings_cache = {row['setting_key']: row['setting_value'] for row in rows}
        _settings_cache_time = time.time()
        print("[SETTINGS] Loaded into cache.")
    except Exception as e:
        print(f"[SETTINGS] Load error: {e}")
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

def get_setting(key, default=None):
    """Ambil nilai setting (dengan cache). Jika tidak ada, gunakan default."""
    global _settings_cache, _settings_cache_time
    if time.time() - _settings_cache_time > CACHE_TTL:
        load_settings()
    return _settings_cache.get(key, default)

def update_setting(key, value):
    """Update satu setting di database dan langsung perbarui cache."""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO app_settings (setting_key, setting_value)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
        """, (key, value))
        conn.commit()
        _settings_cache[key] = value
        return True
    except Exception as e:
        print(f"[SETTINGS] Update error: {e}")
        return False
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def send_telegram_msg(message, is_urgent=False):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    if is_urgent:
        prefix = "🚨 DARURAT 🚨\n\n"
    else:
        prefix = "📊 Monitoring Ruang Server\n\n"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"{prefix}{message}"
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code != 200:
            print(f"[TELEGRAM] Failed -> {response.text}")
    except Exception as e:
        print(f"[TELEGRAM] Error -> {e}")

def log_event(event_type, deskripsi, status):
    conn = get_db_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        query = """
            INSERT INTO event_logs (event_type, deskripsi, status)
            VALUES (%s, %s, %s)
        """
        cursor.execute(query, (event_type, deskripsi, status))
        conn.commit()
        status_text = ["AMAN", "WARNING", "BAHAYA"][status] if status in [0,1,2] else "UNKNOWN"
        print(f"[EVENT] {event_type} | {status_text} | {deskripsi}")
    except Exception as e:
        print(f"[EVENT] Error -> {e}")
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

def save_monitoring_log(suhu, lembab, amper, watt, pintu):
    conn = get_db_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        query = """
            INSERT INTO monitoring_logs
            (suhu, kelembapan, arus_listrik, daya_watt, status_pintu, power_status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        status_pintu_db = 1 if pintu == "terbuka" else 0
        amper_bawah_str = get_setting('amper_bawah', '0.190')
        AMPER_BAWAH = safe_float(amper_bawah_str, 0.190)
        power_status_db = 0 if amper < AMPER_BAWAH else 1

        values = (suhu, lembab, amper, round(watt, 1), status_pintu_db, power_status_db)
        cursor.execute(query, values)
        conn.commit()
        print("[DATABASE] Monitoring log saved.")
    except Exception as e:
        print(f"[DATABASE] Insert Error -> {e}")
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

def shutdown_system(reason):
    print(f"[SYSTEM] Shutdown dipanggil. Alasan: {reason}")
    msg_shutdown = (
        f"⚠️ SYSTEM SHUTDOWN ⚠️\n"
        f"Alasan: {reason}\n"
        f"Server akan dimatikan."
    )
    send_telegram_msg(msg_shutdown, is_urgent=True)
    log_event("SYSTEM_SHUTDOWN", msg_shutdown, STATUS_BAHAYA)

    alert_state.server_hidup = False

    if reason.startswith("Listrik utama padam"):
        alert_state.shutdown_listrik_sent = True
    elif reason.startswith("Overheat kritis"):
        alert_state.shutdown_overheat_sent = True

    if os.name == "nt":
        os.system("shutdown /s /t 0")
    else:
        os.system("sudo shutdown -h now")

STATUS_AMAN = 0
STATUS_WARNING = 1
STATUS_BAHAYA = 2

PINTU_TERTUTUP = 0
PINTU_TERBUKA = 1

POWER_OFF = 0
POWER_ON = 1

class AlertState:
    suhu_tinggi = False
    suhu_rendah = False
    overheat_kritis = False
    waktu_overheat = 0
    shutdown_overheat_sent = False
    
    lembab_tinggi = False
    lembab_rendah = False
    
    daya_overload = False
    
    listrik_mati = False
    waktu_listrik_mati = 0
    shutdown_listrik_sent = False
    
    server_hidup = False
    server_pernah_hidup = False
    
    pintu_terbuka = False
    waktu_buka_pintu = 0
    alarm_pintu_sent = False

alert_state = AlertState()

def handle_suhu(suhu):
    SUHU_ATAS = safe_float(get_setting('suhu_atas', '35.0'), 35.0)
    SUHU_KRITIS = safe_float(get_setting('suhu_kritis', '40.0'), 40.0)
    SUHU_BAWAH = safe_float(get_setting('suhu_bawah', '18.0'), 18.0)
    DURASI_MAKS_OVERHEAT = safe_float(get_setting('durasi_maks_overheat', '300'), 300)

    if suhu > SUHU_ATAS and not alert_state.suhu_tinggi:
        msg_text = (
            f"⚠️ PERINGATAN SUHU TINGGI\n"
            f"Suhu ruang server mencapai {suhu:.1f} °C\n"
            f"Batas aman: {SUHU_ATAS} °C"
        )
        send_telegram_msg(msg_text)
        log_event("SUHU_TINGGI", f"Suhu mencapai {suhu:.1f}°C", STATUS_WARNING)
        alert_state.suhu_tinggi = True
    elif suhu <= SUHU_ATAS and alert_state.suhu_tinggi:
        msg_text = f"✅ Suhu kembali normal: {suhu:.1f} °C"
        send_telegram_msg(msg_text)
        log_event("SUHU_NORMAL", f"Suhu kembali normal: {suhu:.1f}°C", STATUS_AMAN)
        alert_state.suhu_tinggi = False
        alert_state.overheat_kritis = False
        alert_state.waktu_overheat = 0
        alert_state.shutdown_overheat_sent = False

    if suhu >= SUHU_KRITIS:
        if not alert_state.overheat_kritis:
            msg_text = (
                f"🔥 SUHU KRITIS 🔥\n"
                f"Suhu ruang server mencapai {suhu:.1f} °C\n"
                f"Shutdown otomatis dalam {DURASI_MAKS_OVERHEAT//60} menit."
            )
            send_telegram_msg(msg_text, is_urgent=True)
            log_event("SUHU_KRITIS", f"Suhu kritis: {suhu:.1f}°C", STATUS_BAHAYA)
            alert_state.overheat_kritis = True
            alert_state.waktu_overheat = time.time()
            alert_state.shutdown_overheat_sent = False
        else:
            durasi_overheat = time.time() - alert_state.waktu_overheat
            if durasi_overheat >= DURASI_MAKS_OVERHEAT and not alert_state.shutdown_overheat_sent:
                shutdown_system("Overheat kritis - Suhu melewati batas selama 5 menit")

    if suhu < SUHU_BAWAH and not alert_state.suhu_rendah:
        msg_text = (
            f"❄️ PERINGATAN SUHU RENDAH\n"
            f"Suhu ruang server {suhu:.1f} °C\n"
            f"Batas aman: {SUHU_BAWAH} °C"
        )
        send_telegram_msg(msg_text)
        log_event("SUHU_RENDAH", f"Suhu rendah: {suhu:.1f}°C", STATUS_WARNING)
        alert_state.suhu_rendah = True
    elif suhu >= SUHU_BAWAH and alert_state.suhu_rendah:
        msg_text = f"✅ Suhu dingin kembali normal: {suhu:.1f} °C"
        send_telegram_msg(msg_text)
        log_event("SUHU_NORMAL", f"Suhu kembali normal: {suhu:.1f}°C", STATUS_AMAN)
        alert_state.suhu_rendah = False

def handle_kelembapan(lembab):
    LEMBAB_ATAS = safe_float(get_setting('lembab_atas', '70.0'), 70.0)
    LEMBAB_BAWAH = safe_float(get_setting('lembab_bawah', '30.0'), 30.0)

    if lembab > LEMBAB_ATAS and not alert_state.lembab_tinggi:
        msg_text = (
            f"💧 KELEMBAPAN TINGGI\n"
            f"Kelembapan mencapai {lembab:.0f}%\n"
            f"Batas aman: {LEMBAB_ATAS}%"
        )
        send_telegram_msg(msg_text)
        log_event("KELEMBAPAN_TINGGI", f"Kelembapan tinggi: {lembab:.0f}%", STATUS_WARNING)
        alert_state.lembab_tinggi = True
    elif lembab <= LEMBAB_ATAS and alert_state.lembab_tinggi:
        msg_text = f"✅ Kelembapan kembali normal: {lembab:.0f}%"
        send_telegram_msg(msg_text)
        log_event("KELEMBAPAN_NORMAL", f"Kelembapan normal: {lembab:.0f}%", STATUS_AMAN)
        alert_state.lembab_tinggi = False

    if lembab < LEMBAB_BAWAH and not alert_state.lembab_rendah:
        msg_text = (
            f"🏜️ KELEMBAPAN RENDAH\n"
            f"Kelembapan mencapai {lembab:.0f}%\n"
            f"Batas aman: {LEMBAB_BAWAH}%"
        )
        send_telegram_msg(msg_text)
        log_event("KELEMBAPAN_RENDAH", f"Kelembapan rendah: {lembab:.0f}%", STATUS_WARNING)
        alert_state.lembab_rendah = True
    elif lembab >= LEMBAB_BAWAH and alert_state.lembab_rendah:
        msg_text = f"✅ Kelembapan rendah kembali normal: {lembab:.0f}%"
        send_telegram_msg(msg_text)
        log_event("KELEMBAPAN_NORMAL", f"Kelembapan normal: {lembab:.0f}%", STATUS_AMAN)
        alert_state.lembab_rendah = False

def handle_listrik(amper, watt):
    AMPER_BAWAH = safe_float(get_setting('amper_bawah', '0.190'), 0.190)
    WATT_ATAS = safe_float(get_setting('watt_atas', '3500.0'), 3500.0)
    DURASI_MAKS_ARUS_MATI = safe_float(get_setting('durasi_maks_arus_mati', '300'), 300)

    current_time = time.time()
    
    if amper < AMPER_BAWAH:
        if not alert_state.listrik_mati:
            msg_text = (
                f"⚠️ LISTRIK UTAMA PADAM ⚠️\n"
                f"Arus terdeteksi: {amper:.2f} A\n"
                f"Server akan shutdown otomatis dalam {DURASI_MAKS_ARUS_MATI//60} menit."
            )
            send_telegram_msg(msg_text, is_urgent=True)
            log_event("LISTRIK_PADAM", f"Listrik utama padam - Arus: {amper:.2f}A", STATUS_BAHAYA)
            alert_state.listrik_mati = True
            alert_state.waktu_listrik_mati = current_time
            alert_state.shutdown_listrik_sent = False
        else:
            durasi_mati = current_time - alert_state.waktu_listrik_mati
            if durasi_mati >= DURASI_MAKS_ARUS_MATI and not alert_state.shutdown_listrik_sent:
                shutdown_system("Listrik utama padam selama 5 menit")
    else:
        if alert_state.listrik_mati:
            msg_text = (
                f"✅ LISTRIK KEMBALI NORMAL ✅\n"
                f"Arus terdeteksi: {amper:.2f} A\n"
                f"Shutdown otomatis dibatalkan."
            )
            send_telegram_msg(msg_text)
            log_event("LISTRIK_NORMAL", f"Listrik kembali normal - Arus: {amper:.2f}A", STATUS_AMAN)
            alert_state.listrik_mati = False
            alert_state.waktu_listrik_mati = 0
            alert_state.shutdown_listrik_sent = False

        if not alert_state.server_hidup:
            msg_text = (
                f"✅ SERVER HIDUP ✅\n"
                f"Arus terdeteksi: {amper:.2f} A\n"
                f"Server berhasil dinyalakan dan beroperasi normal."
            )
            send_telegram_msg(msg_text)
            log_event("SERVER_HIDUP", f"Server hidup - Arus: {amper:.2f}A", STATUS_AMAN)
            alert_state.server_hidup = True
            alert_state.server_pernah_hidup = True

        if watt > WATT_ATAS:
            if not alert_state.daya_overload:
                msg_text = (
                    f"⚡ BEBAN DAYA BERLEBIH ⚡\n"
                    f"Arus: {amper:.2f} A\n"
                    f"Daya: {watt:.1f} Watt\n"
                    f"Batas aman: {WATT_ATAS} Watt"
                )
                send_telegram_msg(msg_text, is_urgent=True)
                log_event("DAYA_OVERLOAD", f"Daya overload: {watt:.1f}W", STATUS_BAHAYA)
                alert_state.daya_overload = True
        else:
            if alert_state.daya_overload:
                msg_text = (
                    f"✅ DAYA KEMBALI NORMAL\n"
                    f"Arus: {amper:.2f} A\n"
                    f"Daya: {watt:.1f} Watt"
                )
                send_telegram_msg(msg_text)
                log_event("DAYA_NORMAL", f"Daya normal: {watt:.1f}W", STATUS_AMAN)
                alert_state.daya_overload = False

def handle_pintu(pintu, alarm_pintu_esp=False):
    DURASI_MAKS_PINTU = safe_float(get_setting('durasi_maks_pintu', '300'), 300)

    is_pintu_terbuka = pintu == "terbuka"

    if is_pintu_terbuka != alert_state.pintu_terbuka:
        alert_state.pintu_terbuka = is_pintu_terbuka
        if is_pintu_terbuka:
            status_msg = "🚪 PINTU RUANG SERVER DIBUKA 🚪"
            send_telegram_msg(status_msg, is_urgent=True)
            log_event("PINTU_TERBUKA", "Pintu ruang server dibuka", STATUS_WARNING)
            alert_state.waktu_buka_pintu = time.time()
            alert_state.alarm_pintu_sent = False
        else:
            status_msg = "✅ PINTU RUANG SERVER DITUTUP"
            send_telegram_msg(status_msg)
            log_event("PINTU_TERTUTUP", "Pintu ruang server ditutup", STATUS_AMAN)
            alert_state.waktu_buka_pintu = 0
            alert_state.alarm_pintu_sent = False

    if alert_state.pintu_terbuka:
        durasi_pintu = time.time() - alert_state.waktu_buka_pintu
        if durasi_pintu >= DURASI_MAKS_PINTU or alarm_pintu_esp:
            if not alert_state.alarm_pintu_sent:
                msg_pintu_lama = (
                    "🔴 PERINGATAN KEAMANAN 🔴\n"
                    "Pintu ruang server terbuka lebih dari 5 menit!"
                )
                send_telegram_msg(msg_pintu_lama, is_urgent=True)
                log_event("PINTU_ALARM", "Pintu terbuka > 5 menit - ALARM!", STATUS_BAHAYA)
                alert_state.alarm_pintu_sent = True

def on_mqtt_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0 or str(reason_code).lower() == "success":
        print(f"[MQTT] Connected -> {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC)
        print(f"[MQTT] Subscribe -> {MQTT_TOPIC}")
    else:
        print(f"[MQTT] Failed Connect -> {reason_code}")

def on_mqtt_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):
    print(f"[MQTT] Disconnected -> {reason_code}")

def on_mqtt_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        suhu = safe_float(data.get("suhu"), 0)
        lembab = safe_float(data.get("lembab"), 0)
        amper = safe_float(data.get("amper"), 0)
        watt = safe_float(data.get("watt"), 0)
        pintu = str(data.get("pintu", "tertutup")).lower()
        alarm_pintu_esp = (str(data.get("alarm_pintu", "normal")).lower() == "aktif")

        print(
            f"[DATA] "
            f"Suhu={suhu:.1f}°C | "
            f"Lembab={lembab:.1f}% | "
            f"Arus={amper:.2f}A | "
            f"Daya={watt:.1f}W | "
            f"Pintu={pintu} | "
            f"AlarmPintu={alarm_pintu_esp}"
        )

        handle_suhu(suhu)
        handle_kelembapan(lembab)
        handle_listrik(amper, watt)
        handle_pintu(pintu, alarm_pintu_esp)
        save_monitoring_log(suhu, lembab, amper, watt, pintu)

    except Exception as e:
        print(f"[ERROR MQTT MESSAGE] {e}")

def mqtt_worker():
    client_id = f"Flask_Monitor_{uuid.uuid4().hex[:8]}"
    print(f"[MQTT] Worker Started ID={client_id}")

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
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
        print(f"[MQTT] Fatal Error -> {e}")
    finally:
        client.loop_stop()
        print("[MQTT] Worker Stopped")

def start_mqtt_thread():
    mqtt_thread = threading.Thread(target=mqtt_worker, daemon=True)
    mqtt_thread.start()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

class User(UserMixin):
    def __init__(self, id, nama, email):
        self.id = id
        self.nama = nama
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
        user = cursor.fetchone()
        if user:
            return User(id=user["id"], nama=user["nama"], email=user["email"])
    except Exception as e:
        print(f"[USER] Load Error -> {e}")
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass
    return None

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
                user = cursor.fetchone()
                if user and check_password_hash(user["password"], password):
                    user_obj = User(id=user["id"], nama=user["nama"], email=user["email"])
                    login_user(user_obj)
                    return redirect(url_for("index"))
                flash("Email atau password salah.", "danger")
            except Exception as e:
                print(f"[LOGIN] Error -> {e}")
                flash("Terjadi kesalahan saat login.", "danger")
            finally:
                try:
                    cursor.close()
                    conn.close()
                except Exception:
                    pass
        else:
            flash("Database gagal terhubung.", "danger")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    return render_template("index.html")

@app.route("/logs")
@login_required
def logs():
    conn = get_db_connection()
    logs_data = []
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT *
                FROM monitoring_logs
                ORDER BY created_at DESC
                LIMIT 500
            """)
            logs_data = cursor.fetchall()
        except Exception as e:
            print(f"[LOGS] Error -> {e}")
        finally:
            try:
                cursor.close()
                conn.close()
            except Exception:
                pass
    return render_template("logs.html", logs=logs_data)

@app.route("/events")
@login_required
def events():
    conn = get_db_connection()
    events_data = []
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT *
                FROM event_logs
                ORDER BY created_at DESC
                LIMIT 300
            """)
            events_data = cursor.fetchall()
        except Exception as e:
            print(f"[EVENTS] Error -> {e}")
        finally:
            try:
                cursor.close()
                conn.close()
            except Exception:
                pass
    return render_template("events.html", events=events_data)

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    keys = [
        'suhu_atas', 'suhu_kritis', 'suhu_bawah',
        'lembab_atas', 'lembab_bawah',
        'watt_atas', 'amper_bawah',
        'durasi_maks_pintu', 'durasi_maks_arus_mati', 'durasi_maks_overheat'
    ]

    if request.method == "POST":
        for key in keys:
            value = request.form.get(key)
            if value is not None:
                update_setting(key, value)
        flash("Pengaturan berhasil diperbarui.", "success")
        return redirect(url_for("settings"))
    
    load_settings()
    current = {k: _settings_cache.get(k, '') for k in keys}
    return render_template("settings.html", settings=current)

@app.route("/api/latest")
@login_required
def api_latest():
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT *
                FROM monitoring_logs
                ORDER BY id DESC
                LIMIT 1
            """)
            latest = cursor.fetchone()
            if latest:
                latest["created_at"] = latest["created_at"].strftime("%Y-%m-%d %H:%M:%S")
                return jsonify(latest)
        except Exception as e:
            print(f"[API LATEST] Error -> {e}")
        finally:
            try:
                cursor.close()
                conn.close()
            except Exception:
                pass
    return jsonify({})

@app.route("/api/chart")
@login_required
def api_chart():
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT *
                FROM
                (
                    SELECT *
                    FROM monitoring_logs
                    ORDER BY id DESC
                    LIMIT 30
                ) sub
                ORDER BY id ASC
            """)
            records = cursor.fetchall()
            data = {
                "labels": [r["created_at"].strftime("%H:%M") for r in records],
                "suhu": [float(r["suhu"]) for r in records],
                "watt": [float(r["daya_watt"]) for r in records],
                "amper": [float(r["arus_listrik"]) for r in records]
            }
            return jsonify(data)
        except Exception as e:
            print(f"[API CHART] Error -> {e}")
        finally:
            try:
                cursor.close()
                conn.close()
            except Exception:
                pass
    return jsonify({})

if __name__ == "__main__":
    print(f"[FLASK] Running {APP_HOST}:{APP_PORT}")

    load_settings()

    db_test = get_db_connection()
    if db_test:
        print("[DATABASE] Connected")
        db_test.close()
    else:
        print("[DATABASE] Failed")

    start_mqtt_thread()

    app.run(
        debug=True,
        host=APP_HOST,
        port=APP_PORT,
        use_reloader=False
    )