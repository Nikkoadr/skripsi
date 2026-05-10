Langkah-langkah Instalasi

1. Persiapan Lingkungan (Virtual Environment)
Disarankan menggunakan virtual environment agar tidak terjadi konflik library.

# Buat virtual environment
python -m venv venv

# Aktifkan (Windows)
venv\Scripts\activate

# Aktifkan (macOS/Linux)
source venv/bin/activate

2. Instalasi Library
Gunakan file requirements.txt yang sudah tersedia untuk menginstal semua kebutuhan sekaligus:

pip install -r requirements.txt

3. Konfigurasi Database
Buka aplikasi manajemen database (seperti phpMyAdmin).

Buat database baru dengan nama skripsi.

Import file skripsi.sql ke dalam database tersebut.

4. Konfigurasi Environment
Salin file .env.example menjadi .env dan sesuaikan kredensial database Anda:

cp .env.example .env
Buka file .env dan isi bagian DB_USER, DB_PASSWORD, dan DB_NAME.

Cara Menjalankan Aplikasi
Menjalankan Flask Server
Pastikan virtual environment masih aktif, lalu jalankan:

python app.py
Aplikasi akan berjalan di: http://127.0.0.1:5000

Menyiapkan ESP32
Buka file ESP32.ino menggunakan Arduino IDE.

Pastikan library yang dibutuhkan di Arduino IDE sudah terinstal.

Sesuaikan SSID, PASSWORD WiFi, dan IP Address server (IP komputer) pada kode program.

Upload kode ke perangkat ESP32.