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


# =========================================================
# LOAD ENV
# =========================================================
load_dotenv()


# =========================================================
# FLASK APP
# =========================================================
app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not app.secret_key:
    raise ValueError("FLASK_SECRET_KEY belum diatur pada file .env")


# =========================================================
# APP CONFIG
# =========================================================
APP_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("FLASK_PORT", 5000))


# =========================================================
# DATABASE CONFIG
# =========================================================
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")


# =========================================================
# MQTT CONFIG
# =========================================================
MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_TOPIC = os.getenv("MQTT_TOPIC")


# =========================================================
# TELEGRAM CONFIG
# =========================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# =========================================================
# BATAS SENSOR
# =========================================================
SUHU_ATAS = 35.0
SUHU_KRITIS = 40.0
SUHU_BAWAH = 18.0

LEMBAB_ATAS = 70.0
LEMBAB_BAWAH = 30.0

WATT_ATAS = 3500.0
AMPER_BAWAH = 0.5


# =========================================================
# DURASI DETEKSI
# =========================================================
DURASI_MAKS_PINTU = 300
DURASI_MAKS_ARUS_MATI = 300
DURASI_MAKS_OVERHEAT = 300


# =========================================================
# STATUS DATABASE
# =========================================================
STATUS_AMAN = 0
STATUS_WARNING = 1
STATUS_BAHAYA = 2

PINTU_TERTUTUP = 0
PINTU_TERBUKA = 1

POWER_OFF = 0
POWER_ON = 1


# =========================================================
# ALERT STATE
# =========================================================
class AlertState:
    suhu_tinggi = False
    suhu_rendah = False

    overheat_kritis = False
    waktu_overheat = 0
    shutdown_overheat_sent = False

    lembab_tinggi = False
    lembab_rendah = False

    daya_overload = False

    arus_mati = False
    waktu_arus_mati = 0
    shutdown_arus_sent = False

    pintu_terbuka = False
    waktu_buka_pintu = 0
    alarm_pintu_sent = False


alert_state = AlertState()


# =========================================================
# DATABASE CONNECTION
# =========================================================
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


# =========================================================
# SAFE FLOAT
# =========================================================
def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# =========================================================
# TELEGRAM
# =========================================================
def send_telegram_msg(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"Monitoring Ruang Server\n\n{message}"
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=5
        )

        if response.status_code != 200:
            print(f"[TELEGRAM] Failed -> {response.text}")

    except Exception as e:
        print(f"[TELEGRAM] Error -> {e}")


# =========================================================
# EVENT LOGGER
# =========================================================
def log_event(event_type, deskripsi, status):
    conn = get_db_connection()

    if not conn:
        return

    try:
        cursor = conn.cursor()

        query = """
            INSERT INTO event_logs
            (
                event_type,
                deskripsi,
                status
            )
            VALUES
            (%s, %s, %s)
        """

        cursor.execute(
            query,
            (
                event_type,
                deskripsi,
                status
            )
        )

        conn.commit()

        print(f"[EVENT] {event_type} dicatat.")

    except Exception as e:
        print(f"[EVENT] Error -> {e}")

    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass


# =========================================================
# SIMPAN MONITORING LOG
# =========================================================
def save_monitoring_log(suhu, lembab, amper, watt, pintu):
    conn = get_db_connection()

    if not conn:
        return

    try:
        cursor = conn.cursor()

        query = """
            INSERT INTO monitoring_logs
            (
                suhu,
                kelembapan,
                arus_listrik,
                daya_watt,
                status_pintu,
                power_status
            )
            VALUES
            (%s, %s, %s, %s, %s, %s)
        """

        status_pintu_db = (
            PINTU_TERBUKA
            if pintu == "terbuka"
            else PINTU_TERTUTUP
        )

        power_status_db = (
            POWER_OFF
            if amper < AMPER_BAWAH
            else POWER_ON
        )

        values = (
            suhu,
            lembab,
            amper,
            round(watt, 1),
            status_pintu_db,
            power_status_db
        )

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


# =========================================================
# SHUTDOWN SYSTEM
# =========================================================
def shutdown_system(reason):
    print(f"[SYSTEM] Shutdown dipanggil. Alasan: {reason}")

    if os.name == "nt":
        os.system("shutdown /s /t 10")
    else:
        os.system("sudo shutdown -h now")


# =========================================================
# LOGIN MANAGER
# =========================================================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# =========================================================
# USER MODEL
# =========================================================
class User(UserMixin):
    def __init__(self, id, nama, email):
        self.id = id
        self.nama = nama
        self.email = email


# =========================================================
# LOAD USER
# =========================================================
@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()

    if not conn:
        return None

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM users WHERE id=%s",
            (user_id,)
        )

        user = cursor.fetchone()

        if user:
            return User(
                id=user["id"],
                nama=user["nama"],
                email=user["email"]
            )

    except Exception as e:
        print(f"[USER] Load Error -> {e}")

    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

    return None


# =========================================================
# HANDLE SUHU
# =========================================================
def handle_suhu(suhu):
    if suhu > SUHU_ATAS and not alert_state.suhu_tinggi:
        msg_text = (
            f"PERINGATAN SUHU TINGGI\n"
            f"Suhu ruang server mencapai {suhu:.1f} °C"
        )

        send_telegram_msg(msg_text)
        log_event("Suhu", msg_text, STATUS_WARNING)

        alert_state.suhu_tinggi = True

    elif suhu <= SUHU_ATAS and alert_state.suhu_tinggi:
        msg_text = f"Suhu kembali normal: {suhu:.1f} °C"

        send_telegram_msg(msg_text)
        log_event("Suhu", msg_text, STATUS_AMAN)

        alert_state.suhu_tinggi = False
        alert_state.overheat_kritis = False
        alert_state.waktu_overheat = 0
        alert_state.shutdown_overheat_sent = False

    if suhu >= SUHU_KRITIS:
        if not alert_state.overheat_kritis:
            msg_text = (
                f"SUHU KRITIS\n"
                f"Suhu ruang server mencapai {suhu:.1f} °C\n"
                f"Shutdown otomatis dalam 5 menit jika suhu tidak turun."
            )

            send_telegram_msg(msg_text)
            log_event("Suhu", msg_text, STATUS_BAHAYA)

            alert_state.overheat_kritis = True
            alert_state.waktu_overheat = time.time()
            alert_state.shutdown_overheat_sent = False

        else:
            durasi_overheat = time.time() - alert_state.waktu_overheat

            if (
                durasi_overheat >= DURASI_MAKS_OVERHEAT
                and
                not alert_state.shutdown_overheat_sent
            ):
                msg_shutdown = (
                    "OVERHEAT KRITIS\n"
                    "Sistem melakukan shutdown otomatis "
                    "untuk mencegah kerusakan server."
                )

                send_telegram_msg(msg_shutdown)
                log_event("Sistem", msg_shutdown, STATUS_BAHAYA)

                alert_state.shutdown_overheat_sent = True

                shutdown_system("Overheat kritis")

    if suhu < SUHU_BAWAH and not alert_state.suhu_rendah:
        msg_text = (
            f"PERINGATAN SUHU RENDAH\n"
            f"Suhu ruang server {suhu:.1f} °C"
        )

        send_telegram_msg(msg_text)
        log_event("Suhu", msg_text, STATUS_WARNING)

        alert_state.suhu_rendah = True

    elif suhu >= SUHU_BAWAH and alert_state.suhu_rendah:
        msg_text = f"Suhu dingin kembali normal: {suhu:.1f} °C"

        send_telegram_msg(msg_text)
        log_event("Suhu", msg_text, STATUS_AMAN)

        alert_state.suhu_rendah = False


# =========================================================
# HANDLE KELEMBAPAN
# =========================================================
def handle_kelembapan(lembab):
    if lembab > LEMBAB_ATAS and not alert_state.lembab_tinggi:
        msg_text = (
            f"KELEMBAPAN TINGGI\n"
            f"Kelembapan mencapai {lembab:.0f}%"
        )

        send_telegram_msg(msg_text)
        log_event("Kelembapan", msg_text, STATUS_WARNING)

        alert_state.lembab_tinggi = True

    elif lembab <= LEMBAB_ATAS and alert_state.lembab_tinggi:
        msg_text = f"Kelembapan kembali normal: {lembab:.0f}%"

        send_telegram_msg(msg_text)
        log_event("Kelembapan", msg_text, STATUS_AMAN)

        alert_state.lembab_tinggi = False

    if lembab < LEMBAB_BAWAH and not alert_state.lembab_rendah:
        msg_text = (
            f"KELEMBAPAN RENDAH\n"
            f"Kelembapan mencapai {lembab:.0f}%"
        )

        send_telegram_msg(msg_text)
        log_event("Kelembapan", msg_text, STATUS_WARNING)

        alert_state.lembab_rendah = True

    elif lembab >= LEMBAB_BAWAH and alert_state.lembab_rendah:
        msg_text = (
            f"Kelembapan rendah kembali normal: {lembab:.0f}%"
        )

        send_telegram_msg(msg_text)
        log_event("Kelembapan", msg_text, STATUS_AMAN)

        alert_state.lembab_rendah = False


# =========================================================
# HANDLE LISTRIK
# =========================================================
def handle_listrik(amper, watt):
    if amper < AMPER_BAWAH:
        if not alert_state.arus_mati:
            msg_text = (
                f"LISTRIK PADAM\n"
                f"Arus terdeteksi: {amper:.2f} A\n"
                f"Server akan shutdown otomatis dalam 5 menit."
            )

            send_telegram_msg(msg_text)
            log_event("Listrik", msg_text, STATUS_BAHAYA)

            alert_state.arus_mati = True
            alert_state.waktu_arus_mati = time.time()
            alert_state.shutdown_arus_sent = False
            alert_state.daya_overload = False

        else:
            durasi_mati = time.time() - alert_state.waktu_arus_mati

            if (
                durasi_mati >= DURASI_MAKS_ARUS_MATI
                and
                not alert_state.shutdown_arus_sent
            ):
                msg_shutdown = (
                    "UPS HABIS\n"
                    "Sistem melakukan shutdown server otomatis."
                )

                send_telegram_msg(msg_shutdown)
                log_event("Sistem", msg_shutdown, STATUS_BAHAYA)

                alert_state.shutdown_arus_sent = True

                shutdown_system("Listrik padam / UPS habis")

    elif watt > WATT_ATAS:
        if not alert_state.daya_overload:
            msg_text = (
                f"BEBAN DAYA BERLEBIH\n"
                f"Arus: {amper:.2f} A\n"
                f"Daya: {watt:.1f} Watt"
            )

            send_telegram_msg(msg_text)
            log_event("Listrik", msg_text, STATUS_BAHAYA)

            alert_state.daya_overload = True
            alert_state.arus_mati = False
            alert_state.waktu_arus_mati = 0
            alert_state.shutdown_arus_sent = False

    else:
        if alert_state.arus_mati or alert_state.daya_overload:
            msg_text = (
                f"LISTRIK KEMBALI NORMAL\n"
                f"Arus: {amper:.2f} A\n"
                f"Daya: {watt:.1f} Watt\n"
                f"Shutdown otomatis dibatalkan."
            )

            send_telegram_msg(msg_text)
            log_event("Listrik", msg_text, STATUS_AMAN)

            alert_state.arus_mati = False
            alert_state.waktu_arus_mati = 0
            alert_state.shutdown_arus_sent = False
            alert_state.daya_overload = False


# =========================================================
# HANDLE PINTU
# =========================================================
def handle_pintu(pintu, alarm_pintu_esp=False):
    is_pintu_terbuka = pintu == "terbuka"

    if is_pintu_terbuka != alert_state.pintu_terbuka:
        alert_state.pintu_terbuka = is_pintu_terbuka

        if is_pintu_terbuka:
            status_msg = "PINTU RUANG SERVER DIBUKA"

            send_telegram_msg(status_msg)
            log_event("Keamanan", status_msg, STATUS_WARNING)

            alert_state.waktu_buka_pintu = time.time()
            alert_state.alarm_pintu_sent = False

        else:
            status_msg = "PINTU RUANG SERVER DITUTUP"

            send_telegram_msg(status_msg)
            log_event("Keamanan", status_msg, STATUS_AMAN)

            alert_state.waktu_buka_pintu = 0
            alert_state.alarm_pintu_sent = False

    if alert_state.pintu_terbuka:
        durasi_pintu = time.time() - alert_state.waktu_buka_pintu

        if (
            durasi_pintu >= DURASI_MAKS_PINTU
            or
            alarm_pintu_esp
        ):
            if not alert_state.alarm_pintu_sent:
                msg_pintu_lama = (
                    "PERINGATAN KEAMANAN\n"
                    "Pintu ruang server terbuka lebih dari 5 menit."
                )

                send_telegram_msg(msg_pintu_lama)
                log_event("Keamanan", msg_pintu_lama, STATUS_BAHAYA)

                alert_state.alarm_pintu_sent = True


# =========================================================
# MQTT CONNECT
# =========================================================
def on_mqtt_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0 or str(reason_code).lower() == "success":
        print(f"[MQTT] Connected -> {MQTT_BROKER}:{MQTT_PORT}")

        client.subscribe(MQTT_TOPIC)

        print(f"[MQTT] Subscribe -> {MQTT_TOPIC}")

    else:
        print(f"[MQTT] Failed Connect -> {reason_code}")


# =========================================================
# MQTT DISCONNECT
# =========================================================
def on_mqtt_disconnect(
    client,
    userdata,
    disconnect_flags,
    reason_code,
    properties=None
):
    print(f"[MQTT] Disconnected -> {reason_code}")


# =========================================================
# MQTT MESSAGE
# =========================================================
def on_mqtt_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode("utf-8"))

        suhu = safe_float(data.get("suhu"), 0)
        lembab = safe_float(data.get("lembab"), 0)
        amper = safe_float(data.get("amper"), 0)
        watt = safe_float(data.get("watt"), 0)

        pintu = str(data.get("pintu", "tertutup")).lower()

        alarm_pintu_esp = (
            str(data.get("alarm_pintu", "normal")).lower()
            == "aktif"
        )

        print(
            f"[DATA] "
            f"Suhu={suhu}°C | "
            f"Lembab={lembab}% | "
            f"Arus={amper}A | "
            f"Daya={watt}W | "
            f"Pintu={pintu} | "
            f"AlarmPintu={alarm_pintu_esp}"
        )

        handle_suhu(suhu)
        handle_kelembapan(lembab)
        handle_listrik(amper, watt)
        handle_pintu(pintu, alarm_pintu_esp)

        save_monitoring_log(
            suhu=suhu,
            lembab=lembab,
            amper=amper,
            watt=watt,
            pintu=pintu
        )

    except Exception as e:
        print(f"[ERROR MQTT MESSAGE] {e}")


# =========================================================
# MQTT WORKER
# =========================================================
def mqtt_worker():
    client_id = f"Flask_Monitor_{uuid.uuid4().hex[:8]}"

    print(f"[MQTT] Worker Started ID={client_id}")

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        clean_session=True
    )

    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(
            MQTT_USERNAME,
            MQTT_PASSWORD
        )

    client.on_connect = on_mqtt_connect
    client.on_disconnect = on_mqtt_disconnect
    client.on_message = on_mqtt_message

    client.reconnect_delay_set(
        min_delay=1,
        max_delay=120
    )

    try:
        client.connect_async(
            MQTT_BROKER,
            MQTT_PORT,
            keepalive=30
        )

        client.loop_start()

        while True:
            time.sleep(1)

    except Exception as e:
        print(f"[MQTT] Fatal Error -> {e}")

    finally:
        client.loop_stop()
        print("[MQTT] Worker Stopped")


# =========================================================
# START MQTT THREAD
# =========================================================
def start_mqtt_thread():
    mqtt_thread = threading.Thread(
        target=mqtt_worker,
        daemon=True
    )

    mqtt_thread.start()


start_mqtt_thread()


# =========================================================
# LOGIN
# =========================================================
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

                cursor.execute(
                    "SELECT * FROM users WHERE email=%s",
                    (email,)
                )

                user = cursor.fetchone()

                if (
                    user
                    and
                    check_password_hash(
                        user["password"],
                        password
                    )
                ):
                    user_obj = User(
                        id=user["id"],
                        nama=user["nama"],
                        email=user["email"]
                    )

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


# =========================================================
# LOGOUT
# =========================================================
@app.route("/logout")
@login_required
def logout():
    logout_user()

    return redirect(url_for("login"))


# =========================================================
# DASHBOARD
# =========================================================
@app.route("/")
@login_required
def index():
    return render_template("index.html")


# =========================================================
# LOGS
# =========================================================
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

    return render_template(
        "logs.html",
        logs=logs_data
    )


# =========================================================
# EVENTS
# =========================================================
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

    return render_template(
        "events.html",
        events=events_data
    )


# =========================================================
# API LATEST
# =========================================================
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
                latest["created_at"] = (
                    latest["created_at"]
                    .strftime("%Y-%m-%d %H:%M:%S")
                )

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


# =========================================================
# API CHART
# =========================================================
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
                "labels": [
                    r["created_at"].strftime("%H:%M")
                    for r in records
                ],
                "suhu": [
                    float(r["suhu"])
                    for r in records
                ],
                "watt": [
                    float(r["daya_watt"])
                    for r in records
                ],
                "amper": [
                    float(r["arus_listrik"])
                    for r in records
                ]
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


# =========================================================
# MAIN
# =========================================================
if __name__ == "__main__":
    print(f"[FLASK] Running {APP_HOST}:{APP_PORT}")

    db_test = get_db_connection()

    if db_test:
        print("[DATABASE] Connected")
        db_test.close()
    else:
        print("[DATABASE] Failed")

    app.run(
        debug=True,
        host=APP_HOST,
        port=APP_PORT,
        use_reloader=False
    )