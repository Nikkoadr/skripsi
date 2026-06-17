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
const char* WIFI_SSID = "Toucan";
const char* WIFI_PASS = "Rahasiadong99*";

// =========================================================
// MQTT CONFIG
// =========================================================
const char* MQTT_BROKER = "192.168.1.16";
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
#define CALIBRATION_FACTOR   71.22
#define NOISE_THRESHOLD      0.45
#define VOLTAGE_PLN          220.0
#define ADC_VREF             3.3
#define ADC_RES              4095.0
#define CURRENT_SAMPLES      500
#define SAMPLING_PERIOD      150

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

bool statusPintu = false;
bool alarmPintu  = false;

unsigned long lastMqttSend         = 0;
unsigned long lastOLEDUpdate       = 0;
unsigned long lastReconnectAttempt = 0;
unsigned long waktuPintuTerbuka    = 0;

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
// BACA SENSOR ARUS SCT-013
// =========================================================
void bacaSensorArus() {
  float midpoint = 0.0;
  float sumV     = 0.0;
  uint32_t n     = 0;

  for (int i = 0; i < CURRENT_SAMPLES; i++) {
    midpoint += analogRead(PIN_SCT);
  }

  midpoint /= (float) CURRENT_SAMPLES;

  uint32_t startTime = millis();

  while ((millis() - startTime) < SAMPLING_PERIOD) {
    int raw = analogRead(PIN_SCT);

    float voltage = (raw - midpoint) * ADC_VREF / ADC_RES;

    sumV += voltage * voltage;
    n++;
  }

  if (n == 0) {
    arusRMS  = 0.0;
    dayaWatt = 0.0;
    return;
  }

  float vRMS  = sqrt(sumV / n);
  float iCalc = vRMS * CALIBRATION_FACTOR;

  arusRMS = (iCalc < NOISE_THRESHOLD) ? 0.0 : iCalc;
  dayaWatt = arusRMS * VOLTAGE_PLN;
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
// UPDATE OLED
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

    doc["suhu"]   = suhu;
    doc["lembab"] = lembab;
    doc["amper"]  = arusRMS;
    doc["watt"]   = dayaWatt;
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