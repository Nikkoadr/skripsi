#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>
#include "DHT.h"

// =========================================================
// WIFI CONFIG
// =========================================================
const char* WIFI_SSID = "Nikko Adrian";
const char* WIFI_PASS = "konci123";

// =========================================================
// MQTT CONFIG
// =========================================================
const char* MQTT_BROKER = "172.20.10.2";
const int   MQTT_PORT   = 1883;
const char* MQTT_TOPIC  = "220511203/monitoring/server/data";
const char* MQTT_USER   = "nikkoadr";
const char* MQTT_PASS   = "1234567800";

// =========================================================
// PIN CONFIG
// =========================================================
#define PIN_SCT       34
#define PIN_DHT       23
#define PIN_PINTU     18
#define PIN_BUZZER    14
#define PIN_SDA       21
#define PIN_SCL       22
#define LED_BUILTIN   2

// =========================================================
// SENSOR CONFIG
// =========================================================
#define DHT_TYPE             DHT22
#define VOLTAGE_PLN          220.0

// =========================================================
// KONFIGURASI SCT-013 (DIMODIFIKASI UNTUK KALIBRASI)
// =========================================================
#define ADC_VREF             3.3
#define ADC_RES              4095.0

// === KALIBRASI SCT-013 ===
// Jika pembacaan terlalu tinggi, turunkan CALIBRATION_FACTOR
// Jika pembacaan terlalu rendah, naikkan CALIBRATION_FACTOR
// DEFAULT: 80.0
//#define CALIBRATION_FACTOR   60.0  // <-- SESUAIKAN NILAI INI
#define CALIBRATION_FACTOR   78.0
// Offset untuk koreksi (jika ada pembacaan offset)
// DEFAULT: 0.0
#define OFFSET_CORRECTION    0.03  // <-- SESUAIKAN NILAI INI

#define RMS_SAMPLES          2000
#define OVERSAMPLE           4
#define FILTER_SIZE          5
#define DEADBAND_THRESHOLD   0.02
#define AMPER_BAWAH          0.190

// =========================================================
// OLED CONFIG
// =========================================================
#define SCREEN_WIDTH    128
#define SCREEN_HEIGHT   64
#define OLED_RESET      -1
#define SCREEN_ADDRESS  0x3C

// =========================================================
// TIMER CONFIG
// =========================================================
const unsigned long INTERVAL_MQTT_SEND   = 2000;
const unsigned long INTERVAL_OLED_UPDATE = 1000;
const unsigned long INTERVAL_RECONNECT   = 5000;
const unsigned long AMBANG_WAKTU_PINTU   = 300000; // 5 menit

// =========================================================
// OBJECT INIT
// =========================================================
Adafruit_SSD1306 oled(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);
DHT dht(PIN_DHT, DHT_TYPE);
WiFiClient espClient;
PubSubClient mqtt(espClient);

// =========================================================
// GLOBAL VARIABLE
// =========================================================
float suhu     = 0.0;
float lembab   = 0.0;
float arusRMS  = 0.0;
float dayaWatt = 0.0;
float arusRaw   = 0.0;  // Untuk debugging

bool statusPintu = false;
bool alarmPintu  = false;

unsigned long lastMqttSend         = 0;
unsigned long lastOLEDUpdate       = 0;
unsigned long lastReconnectAttempt = 0;
unsigned long waktuPintuTerbuka    = 0;

// Variabel untuk pembacaan arus
uint16_t adcBuffer[RMS_SAMPLES];
float rmsHistory[FILTER_SIZE];
uint8_t filterIndex = 0;
bool filterFull = false;

// =========================================================
// SETUP WIFI
// =========================================================
void setupWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.print("\n[WIFI] Menghubungkan ke: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  int timeout = 0;

  while (WiFi.status() != WL_CONNECTED && timeout < 20) {
    delay(500);
    Serial.print(".");
    timeout++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WIFI] Terhubung!");
    Serial.print("[WIFI] IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WIFI] Gagal terhubung.");
  }
}

// =========================================================
// RECONNECT MQTT
// =========================================================
bool reconnectMQTT() {
  if (mqtt.connected()) return true;

  Serial.print("[MQTT] Reconnecting... ");

  String clientId = "ESP32_Server_Monitor_";
  clientId += String((uint32_t)ESP.getEfuseMac(), HEX);

  if (mqtt.connect(clientId.c_str(), MQTT_USER, MQTT_PASS)) {
    Serial.println("Sukses!");
    return true;
  }

  Serial.print("Gagal, rc=");
  Serial.println(mqtt.state());

  return false;
}

// =========================================================
// BACA SENSOR DHT22
// =========================================================
void bacaSensorDHT() {
  float suhuBaca   = dht.readTemperature();
  float lembabBaca = dht.readHumidity();

  if (!isnan(suhuBaca)) {
    suhu = suhuBaca;
  }

  if (!isnan(lembabBaca)) {
    lembab = lembabBaca;
  }
}

// =========================================================
// BACA SENSOR ARUS SCT-013 (DENGAN KALIBRASI)
// =========================================================
void bacaSensorArus() {
  //----------------------------------------
  // PASS-1: Oversampling dan pengambilan sampel
  //----------------------------------------
  uint32_t totalADC = 0;

  for (int i = 0; i < RMS_SAMPLES; i++) {
    uint32_t oversample = 0;

    for (int j = 0; j < OVERSAMPLE; j++) {
      oversample += analogRead(PIN_SCT);
    }

    adcBuffer[i] = oversample / OVERSAMPLE;
    totalADC += adcBuffer[i];

    delayMicroseconds(120);
  }

  //----------------------------------------
  // Hitung MIDPOINT (nilai tengah DC offset)
  //----------------------------------------
  float midpoint = (float)totalADC / RMS_SAMPLES;

  //----------------------------------------
  // PASS-2: Hitung RMS
  //----------------------------------------
  double sumSquare = 0;

  for (int i = 0; i < RMS_SAMPLES; i++) {
    float voltage = (adcBuffer[i] - midpoint);
    voltage *= ADC_VREF;
    voltage /= ADC_RES;
    sumSquare += voltage * voltage;
  }

  float vrms = sqrt(sumSquare / RMS_SAMPLES);
  
  // =========================================================
  // APLIKASI KALIBRASI
  // =========================================================
  float current = vrms * CALIBRATION_FACTOR;
  
  // Terapkan offset correction
  if (current > 0) {
    current = current - OFFSET_CORRECTION;
  }
  
  // Simpan nilai raw untuk debugging
  arusRaw = current;

  //----------------------------------------
  // Moving Average (filter untuk stabilitas)
  //----------------------------------------
  rmsHistory[filterIndex] = current;
  filterIndex++;

  if (filterIndex >= FILTER_SIZE) {
    filterIndex = 0;
    filterFull = true;
  }

  uint8_t jumlah = filterFull ? FILTER_SIZE : filterIndex;
  float total = 0;

  for (int i = 0; i < jumlah; i++) {
    total += rmsHistory[i];
  }

  current = total / jumlah;

  //----------------------------------------
  // Deadband (hilangkan noise)
  //----------------------------------------
  if (current < DEADBAND_THRESHOLD) {
    current = 0;
  }

  // =========================================================
  // CEK AMBANG BATAS ARUS
  // Jika arus di bawah 0.190A, set ke 0
  // =========================================================
  if (current < AMPER_BAWAH) {
    current = 0;
  }

  arusRMS = current;
  dayaWatt = arusRMS * VOLTAGE_PLN;
  
  // =========================================================
  // DEBUG: Tampilkan nilai di Serial Monitor
  // =========================================================
  static unsigned long lastDebugPrint = 0;
  if (millis() - lastDebugPrint > 3000) {
    Serial.print("[DEBUG] Raw: ");
    Serial.print(arusRaw, 2);
    Serial.print(" A | Filtered: ");
    Serial.print(arusRMS, 2);
    Serial.println(" A");
    lastDebugPrint = millis();
  }
}

// =========================================================
// BACA STATUS PINTU DAN ALARM
// =========================================================
void handleSecurity() {
  statusPintu = (digitalRead(PIN_PINTU) == HIGH);

  if (statusPintu) {
    if (waktuPintuTerbuka == 0) {
      waktuPintuTerbuka = millis();
    }

    alarmPintu = (millis() - waktuPintuTerbuka > AMBANG_WAKTU_PINTU);
  } else {
    waktuPintuTerbuka = 0;
    alarmPintu = false;
  }

  if (alarmPintu) {
    bool blinkState = (millis() / 500) % 2;
    digitalWrite(LED_BUILTIN, blinkState);
    digitalWrite(PIN_BUZZER, blinkState);
  } else {
    digitalWrite(LED_BUILTIN, LOW);
    digitalWrite(PIN_BUZZER, LOW);
  }
}

// =========================================================
// UPDATE OLED (DITAMBAHKAN ARUS RAW)
// =========================================================
void updateOLED() {
  if (millis() - lastOLEDUpdate < INTERVAL_OLED_UPDATE) return;

  oled.clearDisplay();
  oled.setTextSize(1);
  oled.setTextColor(WHITE);

  oled.setCursor(0, 0);
  oled.println(F(" MONITOR R. SERVER "));
  oled.println(F("---------------------"));

  oled.printf("Suhu   : %.1f C\n", suhu);
  oled.printf("Lembab : %.0f %%\n", lembab);
  oled.printf("Arus   : %.2f A\n", arusRMS);
  oled.printf("Daya   : %.0f Watt\n", dayaWatt);
  
  // Tampilkan nilai raw untuk debugging (opsional)
  // oled.printf("Raw    : %.3f A\n", arusRaw);

  if (alarmPintu) {
    oled.println(F("Pintu  : !ALARM!"));
  } else {
    oled.printf("Pintu  : %s\n", statusPintu ? "TERBUKA" : "TERTUTUP");
  }

  oled.display();

  lastOLEDUpdate = millis();
}

// =========================================================
// PUBLISH MQTT
// =========================================================
void publishMQTT() {
  if (millis() - lastMqttSend < INTERVAL_MQTT_SEND) return;

  bacaSensorDHT();

  if (mqtt.connected()) {
    StaticJsonDocument<256> doc;

    float suhuBulat = round(suhu * 10.0) / 10.0;
    float lembabBulat = round(lembab * 10.0) / 10.0;
    float amperBulat = round(arusRMS * 100.0) / 100.0;
    float wattBulat = round(dayaWatt * 10.0) / 10.0;

    doc["suhu"]   = suhuBulat;
    doc["lembab"] = lembabBulat;
    doc["amper"]  = amperBulat;
    doc["watt"]   = wattBulat;
    doc["pintu"]  = statusPintu ? "terbuka" : "tertutup";
    doc["alarm_pintu"] = alarmPintu ? "aktif" : "normal";

    char buffer[256];
    serializeJson(doc, buffer);

    mqtt.publish(MQTT_TOPIC, buffer);

    Serial.print("[MQTT] Sent -> ");
    Serial.println(buffer);
  } else {
    Serial.println("[MQTT] Tidak terkoneksi, data belum dikirim.");
  }

  lastMqttSend = millis();
}

// =========================================================
// SETUP
// =========================================================
void setup() {
  Serial.begin(115200);
  
  Serial.println(F("\n\n========================================"));
  Serial.println(F("  SCT-013 CALIBRATION MODE"));
  Serial.println(F("========================================"));
  Serial.println(F("Tuning CALIBRATION_FACTOR dan OFFSET_CORRECTION"));
  Serial.println(F("========================================\n"));

  Wire.begin(PIN_SDA, PIN_SCL);

  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

  pinMode(PIN_PINTU, INPUT_PULLUP);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(LED_BUILTIN, OUTPUT);

  digitalWrite(PIN_BUZZER, LOW);
  digitalWrite(LED_BUILTIN, LOW);

  if (!oled.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS)) {
    Serial.println(F("[OLED] Gagal inisialisasi!"));
  } else {
    oled.clearDisplay();
    oled.setTextSize(1);
    oled.setTextColor(WHITE);
    oled.setCursor(0, 10);
    oled.println(F("  SYSTEM READY"));
    oled.println(F("  MONITOR AKTIF"));
    oled.display();
  }

  dht.begin();

  setupWiFi();

  mqtt.setServer(MQTT_BROKER, MQTT_PORT);

  Serial.println(F("[SYSTEM] Node Monitoring Ruang Server Aktif!"));
  Serial.println(F("\n[INFO] Gunakan Serial Monitor untuk kalibrasi"));
  Serial.println(F("[INFO] Bandingkan dengan tang amper"));
  Serial.println(F("[INFO] Sesuaikan CALIBRATION_FACTOR & OFFSET_CORRECTION\n"));
}

// =========================================================
// LOOP
// =========================================================
void loop() {
  unsigned long now = millis();

  if (WiFi.status() != WL_CONNECTED) {
    setupWiFi();
  }

  if (!mqtt.connected() && (now - lastReconnectAttempt > INTERVAL_RECONNECT)) {
    reconnectMQTT();
    lastReconnectAttempt = now;
  }

  mqtt.loop();

  bacaSensorArus();
  handleSecurity();
  updateOLED();
  publishMQTT();
}