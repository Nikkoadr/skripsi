import time
import json
import threading
import os
import requests
import uuid

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

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

MQTT_BROKER = os.getenv("MQTT_BROKER", "127.0.0.1")
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

# ============================================================
# FUNGSI UNTUK DEVICE
# ============================================================
def get_or_create_device(device_name):
    """Mencari atau membuat perangkat berdasarkan nama. Mengembalikan (device_id, status)."""
    if not device_name:
        return None, None

    conn = get_db_connection()
    if not conn:
        return None, None

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, status FROM devices WHERE name = %s", (device_name,))
        row = cursor.fetchone()
        if row:
            return row['id'], row['status']
        else:
            cursor.execute("INSERT INTO devices (name, status) VALUES (%s, 'offline')", (device_name,))
            conn.commit()
            device_id = cursor.lastrowid
            return device_id, 'offline'
    except Exception as e:
        print(f"[DEVICE] Error: {e}")
        return None, None
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

def update_device_status(device_id, status='online'):
    """Update status dan last_seen perangkat."""
    if not device_id:
        return
    conn = get_db_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE devices SET status = %s, last_seen = NOW() WHERE id = %s",
            (status, device_id)
        )
        conn.commit()
    except Exception as e:
        print(f"[DEVICE] Update status error: {e}")
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

# ============================================================
# PENGATURAN (SETTINGS)
# ============================================================
def load_settings():
    """Muat seluruh pengaturan dari database ke cache (satu baris)."""
    global _settings_cache, _settings_cache_time
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM app_settings LIMIT 1")
        row = cursor.fetchone()
        if row:
            _settings_cache = {k: row[k] for k in row if k not in ('id', 'updated_at')}
        else:
            cursor.execute("""
                INSERT INTO app_settings (
                    id, suhu_atas, suhu_kritis, suhu_bawah,
                    lembab_atas, lembab_bawah, watt_atas, amper_bawah,
                    durasi_maks_pintu, durasi_maks_arus_mati, durasi_maks_overheat
                ) VALUES (
                    1, 35.0, 40.0, 18.0,
                    70.0, 30.0, 3500.0, 0.190,
                    300, 300, 300
                )
            """)
            conn.commit()
            cursor.execute("SELECT * FROM app_settings LIMIT 1")
            row = cursor.fetchone()
            if row:
                _settings_cache = {k: row[k] for k in row if k not in ('id', 'updated_at')}
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
    global _settings_cache, _settings_cache_time
    if time.time() - _settings_cache_time > CACHE_TTL:
        load_settings()
    return _settings_cache.get(key, default)

def update_setting(key, value):
    """Update satu kolom pengaturan di baris id=1."""
    global _settings_cache

    valid_keys = [
        'suhu_atas', 'suhu_kritis', 'suhu_bawah',
        'lembab_atas', 'lembab_bawah',
        'watt_atas', 'amper_bawah',
        'durasi_maks_pintu', 'durasi_maks_arus_mati', 'durasi_maks_overheat'
    ]
    if key not in valid_keys:
        return False

    if key.startswith('durasi'):
        try:
            val = int(value)
        except ValueError:
            return False
    else:
        try:
            val = float(value)
        except ValueError:
            return False

    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        query = f"UPDATE app_settings SET {key} = %s WHERE id = 1"
        cursor.execute(query, (val,))
        conn.commit()
        _settings_cache[key] = val
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

def format_durasi_teks(detik_val):
    menit = int(detik_val // 60)
    sisa_detik = int(detik_val % 60)
    if menit > 0 and sisa_detik > 0:
        return f"{menit} menit {sisa_detik} detik"
    elif menit > 0:
        return f"{menit} menit"
    else:
        return f"{int(detik_val)} detik"

# ============================================================
# TELEGRAM & LOGGING
# ============================================================
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

def log_event(event_type, deskripsi, status, device_id=None):
    conn = get_db_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        query = """
            INSERT INTO event_logs (event_type, deskripsi, status, device_id)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(query, (event_type, deskripsi, status, device_id))
        conn.commit()
        status_text = ["AMAN", "WARNING", "BAHAYA"][status] if status in [0,1,2] else "UNKNOWN"
        print(f"[EVENT] {event_type} | {status_text} | {deskripsi} (device_id={device_id})")
    except Exception as e:
        print(f"[EVENT] Error -> {e}")
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

def save_monitoring_log(suhu, lembab, amper, watt, pintu, device_id=None):
    conn = get_db_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        query = """
            INSERT INTO monitoring_logs
            (suhu, kelembapan, arus_listrik, daya_watt, status_pintu, power_status, device_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        status_pintu_db = 1 if pintu == "terbuka" else 0
        amper_bawah_str = get_setting('amper_bawah', 0.190)
        AMPER_BAWAH = safe_float(amper_bawah_str, 0.190)
        power_status_db = 0 if amper < AMPER_BAWAH else 1

        values = (suhu, lembab, amper, round(watt, 1), status_pintu_db, power_status_db, device_id)
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
    log_event("SYSTEM_SHUTDOWN", msg_shutdown, STATUS_BAHAYA, device_id=None)

    alert_state.server_hidup = False

    if "Listrik utama" in reason:
        alert_state.shutdown_listrik_sent = True
    elif "Overheat" in reason:
        alert_state.shutdown_overheat_sent = True

    if os.name == "nt":
        os.system("shutdown /s /t 0")
    else:
        os.system("sudo shutdown -h now")

# ============================================================
# KONSTANTA & STATE
# ============================================================
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

# ============================================================
# HANDLER SENSOR
# ============================================================
def handle_suhu(suhu, device_id=None):
    SUHU_ATAS = safe_float(get_setting('suhu_atas', 35.0), 35.0)
    SUHU_KRITIS = safe_float(get_setting('suhu_kritis', 40.0), 40.0)
    SUHU_BAWAH = safe_float(get_setting('suhu_bawah', 18.0), 18.0)
    DURASI_MAKS_OVERHEAT = safe_float(get_setting('durasi_maks_overheat', 300), 300)

    durasi_overheat_teks = format_durasi_teks(DURASI_MAKS_OVERHEAT)

    if suhu > SUHU_ATAS and not alert_state.suhu_tinggi:
        msg_text = (
            f"⚠️ PERINGATAN SUHU TINGGI\n"
            f"Suhu ruang server mencapai {suhu:.1f} °C\n"
            f"Batas aman: {SUHU_ATAS} °C"
        )
        send_telegram_msg(msg_text)
        log_event("SUHU_TINGGI", f"Suhu mencapai {suhu:.1f}°C", STATUS_WARNING, device_id)
        alert_state.suhu_tinggi = True
    elif suhu <= SUHU_ATAS and alert_state.suhu_tinggi:
        msg_text = f"✅ Suhu kembali normal: {suhu:.1f} °C"
        send_telegram_msg(msg_text)
        log_event("SUHU_NORMAL", f"Suhu kembali normal: {suhu:.1f}°C", STATUS_AMAN, device_id)
        alert_state.suhu_tinggi = False
        alert_state.overheat_kritis = False
        alert_state.waktu_overheat = 0
        alert_state.shutdown_overheat_sent = False

    if suhu >= SUHU_KRITIS:
        if not alert_state.overheat_kritis:
            msg_text = (
                f"🔥 SUHU KRITIS 🔥\n"
                f"Suhu ruang server mencapai {suhu:.1f} °C\n"
                f"Shutdown otomatis dalam {durasi_overheat_teks}."
            )
            send_telegram_msg(msg_text, is_urgent=True)
            log_event("SUHU_KRITIS", f"Suhu kritis: {suhu:.1f}°C", STATUS_BAHAYA, device_id)
            alert_state.overheat_kritis = True
            alert_state.waktu_overheat = time.time()
            alert_state.shutdown_overheat_sent = False
        else:
            durasi_overheat = time.time() - alert_state.waktu_overheat
            if durasi_overheat >= DURASI_MAKS_OVERHEAT and not alert_state.shutdown_overheat_sent:
                shutdown_system(f"Overheat kritis - Suhu melewati batas selama {durasi_overheat_teks}")

    if suhu < SUHU_BAWAH and not alert_state.suhu_rendah:
        msg_text = (
            f"❄️ PERINGATAN SUHU RENDAH\n"
            f"Suhu ruang server {suhu:.1f} °C\n"
            f"Batas aman: {SUHU_BAWAH} °C"
        )
        send_telegram_msg(msg_text)
        log_event("SUHU_RENDAH", f"Suhu rendah: {suhu:.1f}°C", STATUS_WARNING, device_id)
        alert_state.suhu_rendah = True
    elif suhu >= SUHU_BAWAH and alert_state.suhu_rendah:
        msg_text = f"✅ Suhu dingin kembali normal: {suhu:.1f} °C"
        send_telegram_msg(msg_text)
        log_event("SUHU_NORMAL", f"Suhu kembali normal: {suhu:.1f}°C", STATUS_AMAN, device_id)
        alert_state.suhu_rendah = False

def handle_kelembapan(lembab, device_id=None):
    LEMBAB_ATAS = safe_float(get_setting('lembab_atas', 70.0), 70.0)
    LEMBAB_BAWAH = safe_float(get_setting('lembab_bawah', 30.0), 30.0)

    if lembab > LEMBAB_ATAS and not alert_state.lembab_tinggi:
        msg_text = (
            f"💧 KELEMBAPAN TINGGI\n"
            f"Kelembapan mencapai {lembab:.0f}%\n"
            f"Batas aman: {LEMBAB_ATAS}%"
        )
        send_telegram_msg(msg_text)
        log_event("KELEMBAPAN_TINGGI", f"Kelembapan tinggi: {lembab:.0f}%", STATUS_WARNING, device_id)
        alert_state.lembab_tinggi = True
    elif lembab <= LEMBAB_ATAS and alert_state.lembab_tinggi:
        msg_text = f"✅ Kelembapan kembali normal: {lembab:.0f}%"
        send_telegram_msg(msg_text)
        log_event("KELEMBAPAN_NORMAL", f"Kelembapan normal: {lembab:.0f}%", STATUS_AMAN, device_id)
        alert_state.lembab_tinggi = False

    if lembab < LEMBAB_BAWAH and not alert_state.lembab_rendah:
        msg_text = (
            f"🏜️ KELEMBAPAN RENDAH\n"
            f"Kelembapan mencapai {lembab:.0f}%\n"
            f"Batas aman: {LEMBAB_BAWAH}%"
        )
        send_telegram_msg(msg_text)
        log_event("KELEMBAPAN_RENDAH", f"Kelembapan rendah: {lembab:.0f}%", STATUS_WARNING, device_id)
        alert_state.lembab_rendah = True
    elif lembab >= LEMBAB_BAWAH and alert_state.lembab_rendah:
        msg_text = f"✅ Kelembapan rendah kembali normal: {lembab:.0f}%"
        send_telegram_msg(msg_text)
        log_event("KELEMBAPAN_NORMAL", f"Kelembapan normal: {lembab:.0f}%", STATUS_AMAN, device_id)
        alert_state.lembab_rendah = False

def handle_listrik(amper, watt, device_id=None):
    AMPER_BAWAH = safe_float(get_setting('amper_bawah', 0.190), 0.190)
    WATT_ATAS = safe_float(get_setting('watt_atas', 3500.0), 3500.0)
    DURASI_MAKS_ARUS_MATI = safe_float(get_setting('durasi_maks_arus_mati', 300), 300)

    durasi_listrik_teks = format_durasi_teks(DURASI_MAKS_ARUS_MATI)
    current_time = time.time()
    
    if amper < AMPER_BAWAH:
        if not alert_state.listrik_mati:
            msg_text = (
                f"⚠️ LISTRIK UTAMA PADAM ⚠️\n"
                f"Arus terdeteksi: {amper:.2f} A\n"
                f"Server akan shutdown otomatis dalam {durasi_listrik_teks}."
            )
            send_telegram_msg(msg_text, is_urgent=True)
            log_event("LISTRIK_PADAM", f"Listrik utama padam - Arus: {amper:.2f}A", STATUS_BAHAYA, device_id)
            alert_state.listrik_mati = True
            alert_state.waktu_listrik_mati = current_time
            alert_state.shutdown_listrik_sent = False
        else:
            durasi_mati = current_time - alert_state.waktu_listrik_mati
            if durasi_mati >= DURASI_MAKS_ARUS_MATI and not alert_state.shutdown_listrik_sent:
                shutdown_system(f"Listrik utama padam selama {durasi_listrik_teks}")
    else:
        if alert_state.listrik_mati:
            msg_text = (
                f"✅ LISTRIK KEMBALI NORMAL ✅\n"
                f"Arus terdeteksi: {amper:.2f} A\n"
                f"Shutdown otomatis dibatalkan."
            )
            send_telegram_msg(msg_text)
            log_event("LISTRIK_NORMAL", f"Listrik kembali normal - Arus: {amper:.2f}A", STATUS_AMAN, device_id)
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
            log_event("SERVER_HIDUP", f"Server hidup - Arus: {amper:.2f}A", STATUS_AMAN, device_id)
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
                log_event("DAYA_OVERLOAD", f"Daya overload: {watt:.1f}W", STATUS_BAHAYA, device_id)
                alert_state.daya_overload = True
        else:
            if alert_state.daya_overload:
                msg_text = (
                    f"✅ DAYA KEMBALI NORMAL\n"
                    f"Arus: {amper:.2f} A\n"
                    f"Daya: {watt:.1f} Watt"
                )
                send_telegram_msg(msg_text)
                log_event("DAYA_NORMAL", f"Daya normal: {watt:.1f}W", STATUS_AMAN, device_id)
                alert_state.daya_overload = False

def handle_pintu(pintu, alarm_pintu_esp=False, device_id=None):
    DURASI_MAKS_PINTU = safe_float(get_setting('durasi_maks_pintu', 300), 300)
    durasi_pintu_teks = format_durasi_teks(DURASI_MAKS_PINTU)

    is_pintu_terbuka = pintu == "terbuka"

    if is_pintu_terbuka != alert_state.pintu_terbuka:
        alert_state.pintu_terbuka = is_pintu_terbuka
        if is_pintu_terbuka:
            status_msg = "🚪 PINTU RUANG SERVER DIBUKA 🚪"
            send_telegram_msg(status_msg, is_urgent=True)
            log_event("PINTU_TERBUKA", "Pintu ruang server dibuka", STATUS_WARNING, device_id)
            alert_state.waktu_buka_pintu = time.time()
            alert_state.alarm_pintu_sent = False
        else:
            status_msg = "✅ PINTU RUANG SERVER DITUTUP"
            send_telegram_msg(status_msg)
            log_event("PINTU_TERTUTUP", "Pintu ruang server ditutup", STATUS_AMAN, device_id)
            alert_state.waktu_buka_pintu = 0
            alert_state.alarm_pintu_sent = False

    if alert_state.pintu_terbuka:
        durasi_pintu = time.time() - alert_state.waktu_buka_pintu
        if durasi_pintu >= DURASI_MAKS_PINTU or alarm_pintu_esp:
            if not alert_state.alarm_pintu_sent:
                msg_pintu_lama = (
                    "🔴 PERINGATAN KEAMANAN 🔴\n"
                    f"Pintu ruang server terbuka lebih dari {durasi_pintu_teks}!"
                )
                send_telegram_msg(msg_pintu_lama, is_urgent=True)
                log_event("PINTU_ALARM", f"Pintu terbuka > {durasi_pintu_teks} - ALARM!", STATUS_BAHAYA, device_id)
                alert_state.alarm_pintu_sent = True

# ============================================================
# MQTT
# ============================================================
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
        device_name = data.get("device_name", None)
        device_status = data.get("device_status", "online")

        # Proses device
        device_id = None
        if device_name:
            device_id, _ = get_or_create_device(device_name)
            if device_id:
                update_device_status(device_id, device_status if device_status in ['online','offline'] else 'online')

        print(
            f"[DATA] "
            f"Suhu={suhu:.1f}°C | "
            f"Lembab={lembab:.1f}% | "
            f"Arus={amper:.2f}A | "
            f"Daya={watt:.1f}W | "
            f"Pintu={pintu} | "
            f"AlarmPintu={alarm_pintu_esp} | "
            f"Device={device_name} (ID={device_id})"
        )

        handle_suhu(suhu, device_id)
        handle_kelembapan(lembab, device_id)
        handle_listrik(amper, watt, device_id)
        handle_pintu(pintu, alarm_pintu_esp, device_id)
        save_monitoring_log(suhu, lembab, amper, watt, pintu, device_id)

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
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        print(f"[MQTT] Attempting connection to {MQTT_BROKER}:{MQTT_PORT}...")
        client.loop_forever()
    except Exception as e:
        print(f"[MQTT] Fatal Error -> {e}")
    finally:
        print("[MQTT] Worker Stopped")

def start_mqtt_thread():
    mqtt_thread = threading.Thread(target=mqtt_worker, daemon=True)
    mqtt_thread.start()

# ============================================================
# FLASK LOGIN
# ============================================================
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

# ============================================================
# ROUTE AUTHENTIKASI
# ============================================================
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

# ============================================================
# ROUTE UTAMA & HALAMAN
# ============================================================
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
                SELECT ml.*, d.name as device_name
                FROM monitoring_logs ml
                LEFT JOIN devices d ON ml.device_id = d.id
                ORDER BY ml.created_at DESC
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
                SELECT el.*, d.name as device_name
                FROM event_logs el
                LEFT JOIN devices d ON el.device_id = d.id
                ORDER BY el.created_at DESC
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
        form_type = request.form.get("form_type")

        if form_type == "settings_update":
            for key in keys:
                value = request.form.get(key)
                if value is not None:
                    update_setting(key, value.strip())
            flash("Pengaturan sensor berhasil diperbarui.", "success")
            return redirect(url_for("settings"))

        elif form_type == "profile_update":
            nama = request.form.get("nama")
            email = request.form.get("email")
            current_pass = request.form.get("current_password")
            new_pass = request.form.get("new_password")
            confirm_pass = request.form.get("confirm_password")

            try:
                db = get_db_connection()
                cursor = db.cursor(dictionary=True)
                cursor.execute("SELECT * FROM users WHERE id = %s", (current_user.id,))
                user_data = cursor.fetchone()

                if not user_data:
                    flash("Data pengguna tidak ditemukan.", "danger")
                    return redirect(url_for("settings"))

                nama_update = nama.strip() if nama and nama.strip() else user_data["nama"]
                email_update = email.strip() if email and email.strip() else user_data["email"]

                if new_pass:
                    if not current_pass:
                        flash("Masukkan password saat ini untuk konfirmasi perubahan password.", "danger")
                        return redirect(url_for("settings"))
                    
                    if not check_password_hash(user_data["password"], current_pass):
                        flash("Password saat ini salah!", "danger")
                        return redirect(url_for("settings"))

                    if new_pass != confirm_pass:
                        flash("Konfirmasi password baru tidak cocok!", "danger")
                        return redirect(url_for("settings"))

                    hashed_pass = generate_password_hash(new_pass)
                    query = "UPDATE users SET nama = %s, email = %s, password = %s WHERE id = %s"
                    cursor.execute(query, (nama_update, email_update, hashed_pass, current_user.id))
                else:
                    query = "UPDATE users SET nama = %s, email = %s WHERE id = %s"
                    cursor.execute(query, (nama_update, email_update, current_user.id))

                db.commit()
                flash("Profil pengguna berhasil diperbarui.", "success")
            except Exception as e:
                flash(f"Gagal memperbarui profil: {e}", "danger")
            finally:
                if 'cursor' in locals(): cursor.close()
                if 'db' in locals() and db.is_connected(): db.close()

            return redirect(url_for("settings"))

    load_settings()
    current = {k: _settings_cache.get(k, '') for k in keys}
    return render_template("settings.html", settings=current)

# ============================================================
# ROUTE CRUD DEVICES (HANYA POST, DENGAN MODAL)
# ============================================================
@app.route("/devices")
@login_required
def devices():
    """Daftar semua perangkat."""
    conn = get_db_connection()
    devices_data = []
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM devices ORDER BY id DESC")
            devices_data = cursor.fetchall()
        except Exception as e:
            print(f"[DEVICES] Error: {e}")
        finally:
            try:
                cursor.close()
                conn.close()
            except Exception:
                pass
    return render_template("devices.html", devices=devices_data)

@app.route("/devices/add", methods=["POST"])
@login_required
def add_device():
    """Tambah perangkat baru (hanya POST)."""
    name = request.form.get("name", "").strip()
    status = request.form.get("status", "offline")
    if not name:
        flash("Nama perangkat wajib diisi.", "danger")
        return redirect(url_for("devices"))

    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM devices WHERE name = %s", (name,))
            if cursor.fetchone():
                flash("Perangkat dengan nama tersebut sudah ada.", "danger")
                return redirect(url_for("devices"))
            cursor.execute(
                "INSERT INTO devices (name, status) VALUES (%s, %s)",
                (name, status)
            )
            conn.commit()
            flash("Perangkat berhasil ditambahkan.", "success")
        except Exception as e:
            flash(f"Gagal menambahkan: {e}", "danger")
        finally:
            try:
                cursor.close()
                conn.close()
            except Exception:
                pass
    else:
        flash("Koneksi database gagal.", "danger")
    return redirect(url_for("devices"))

@app.route("/devices/edit/<int:device_id>", methods=["POST"])
@login_required
def edit_device(device_id):
    """Edit perangkat (hanya POST)."""
    name = request.form.get("name", "").strip()
    status = request.form.get("status", "offline")
    if not name:
        flash("Nama perangkat wajib diisi.", "danger")
        return redirect(url_for("devices"))

    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM devices WHERE name = %s AND id != %s", (name, device_id))
            if cursor.fetchone():
                flash("Perangkat dengan nama tersebut sudah ada.", "danger")
                return redirect(url_for("devices"))
            cursor.execute(
                "UPDATE devices SET name = %s, status = %s WHERE id = %s",
                (name, status, device_id)
            )
            conn.commit()
            flash("Perangkat berhasil diperbarui.", "success")
        except Exception as e:
            flash(f"Gagal mengupdate: {e}", "danger")
        finally:
            try:
                cursor.close()
                conn.close()
            except Exception:
                pass
    else:
        flash("Koneksi database gagal.", "danger")
    return redirect(url_for("devices"))

@app.route("/devices/delete/<int:device_id>", methods=["POST"])
@login_required
def delete_device(device_id):
    """Hapus perangkat (POST)."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM devices WHERE id = %s", (device_id,))
            conn.commit()
            flash("Perangkat berhasil dihapus.", "success")
        except Exception as e:
            flash(f"Gagal menghapus: {e}", "danger")
        finally:
            try:
                cursor.close()
                conn.close()
            except Exception:
                pass
    else:
        flash("Koneksi database gagal.", "danger")
    return redirect(url_for("devices"))

# ============================================================
# API ROUTES
# ============================================================
@app.route("/api/latest")
@login_required
def api_latest():
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT ml.*, d.name as device_name
                FROM monitoring_logs ml
                LEFT JOIN devices d ON ml.device_id = d.id
                ORDER BY ml.id DESC
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
    return jsonify({
        "suhu": 0,
        "kelembapan": 0,
        "arus_listrik": 0,
        "daya_watt": 0,
        "status_pintu": 0,
        "power_status": 0,
        "created_at": "-",
        "device_name": None
    })

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
    return jsonify({"labels": [], "suhu": [], "watt": [], "amper": []})

# ============================================================
# MAIN
# ============================================================
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