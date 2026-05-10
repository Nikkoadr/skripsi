#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>
#include "DHT.h"

const char* WIFI_SSID   = "Toucan";
const char* WIFI_PASS   = "Rahasiadong99*";
const char* MQTT_BROKER = "192.168.1.16";
const int   MQTT_PORT   = 1883;
const char* MQTT_TOPIC  = "220511203/monitoring/server/data";
const char* MQTT_USER   = "nikkoadr";
const char* MQTT_PASS   = "1234567800";

#define PIN_SCT    34
#define PIN_DHT    23
#define PIN_PINTU  18
#define PIN_BUZZER 19
#define PIN_SDA    21
#define PIN_SCL    22
#define DHT_TYPE   DHT22
#define LED_BUILTIN 2

#define CALIBRATION_FACTOR 71.22
#define NOISE_THRESHOLD    0.45
#define VOLTAGE_PLN        220.0
#define ADC_VREF           3.3
#define ADC_RES            4095.0
#define CURRENT_SAMPLES    500
#define SAMPLING_PERIOD    150

#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1
#define SCREEN_ADDRESS 0x3C

Adafruit_SSD1306 oled(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);
DHT dht(PIN_DHT, DHT_TYPE);
WiFiClient espClient;
PubSubClient mqtt(espClient);

float suhu, lembab, arusRMS, dayaWatt;
bool statusPintu = false;
unsigned long lastMqttSend = 0;
unsigned long lastOLEDUpdate = 0;
unsigned long lastReconnectAttempt = 0;
unsigned long waktuPintuTerbuka = 0; 

const unsigned long AMBANG_WAKTU = 300000;

void setupWiFi() {
  Serial.print("\n[WIFI] Menghubungkan ke: "); Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  int timeout = 0;
  while (WiFi.status() != WL_CONNECTED && timeout < 20) {
    delay(500); Serial.print("."); timeout++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WIFI] Terhubung! IP: " + WiFi.localIP().toString());
  } else {
    Serial.println("\n[WIFI] Gagal Terhubung.");
  }
}

bool reconnectMQTT() {
  if (!mqtt.connected()) {
    Serial.print("[MQTT] Reconnecting...");
    if (mqtt.connect("ESP32_Server_Monitor", MQTT_USER, MQTT_PASS)) {
      Serial.println("Sukses!");
      return true;
    } else {
      Serial.print("Gagal, rc="); Serial.println(mqtt.state());
      return false;
    }
  }
  return true;
}

void bacaSensorArus() {
  float sumV = 0;
  uint32_t n = 0;
  float midPoint = 0;

  for(int i = 0; i < CURRENT_SAMPLES; i++) {
    midPoint += analogRead(PIN_SCT);
  }
  midPoint /= (float)CURRENT_SAMPLES;

  uint32_t start_time = millis();
  while((millis() - start_time) < SAMPLING_PERIOD) {
    int raw = analogRead(PIN_SCT);
    float voltage = (raw - midPoint) * ADC_VREF / ADC_RES;
    sumV += (voltage * voltage);
    n++;
  }

  float vRMS = sqrt(sumV / n);
  float iCalc = vRMS * CALIBRATION_FACTOR;

  arusRMS = (iCalc < NOISE_THRESHOLD) ? 0 : iCalc;
  dayaWatt = arusRMS * VOLTAGE_PLN;
}

void handleDisplayAndSecurity() {
  statusPintu = (digitalRead(PIN_PINTU) == HIGH);

  if (statusPintu) {
    if (waktuPintuTerbuka == 0) {
      waktuPintuTerbuka = millis();
    }

if (millis() - waktuPintuTerbuka > AMBANG_WAKTU) {

  bool blinkState = (millis() / 500) % 2;

  digitalWrite(LED_BUILTIN, blinkState);
  digitalWrite(PIN_BUZZER, HIGH);

}
  } else {
    waktuPintuTerbuka = 0;
    digitalWrite(LED_BUILTIN, LOW);
    digitalWrite(PIN_BUZZER, LOW);
  }

  if (millis() - lastOLEDUpdate < 1000) return;

  oled.clearDisplay();
  oled.setTextSize(1);
  oled.setTextColor(WHITE);
  oled.setCursor(0, 0);
  oled.println(F(" MONITOR R. Server "));
  oled.println(F("---------------------"));
  oled.printf("Suhu   : %.1f C\n", suhu);
  oled.printf("Lembab : %.0f %%\n", lembab);
  oled.printf("Arus   : %.2f A\n", arusRMS);
  oled.printf("Daya   : %.0f Watt\n", dayaWatt);

  if (waktuPintuTerbuka != 0 && (millis() - waktuPintuTerbuka > AMBANG_WAKTU)) {
      oled.println(F("Pintu  : !ALARM!"));
    } else {
      oled.printf("Pintu  : %s", statusPintu ? "TERBUKA" : "TERTUTUP");
    }

  oled.display();
  
  lastOLEDUpdate = millis();
}

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
  
  if(!oled.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS)) {
    Serial.println(F("OLED Gagal!"));
  } else {
    oled.clearDisplay();
    oled.setCursor(0, 10);
    oled.println(F("   SYSTEM READY   "));
    oled.display();
  }

  dht.begin();
  setupWiFi();
  mqtt.setServer(MQTT_BROKER, MQTT_PORT);
  
  Serial.println(F("[SYSTEM] Node Monitoring Aktif!"));
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) setupWiFi();
  
  unsigned long now = millis();
  if (!mqtt.connected() && (now - lastReconnectAttempt > 5000)) {
    reconnectMQTT();
    lastReconnectAttempt = now;
  }
  mqtt.loop();

  bacaSensorArus();

  if (now - lastMqttSend >= 2000) {
    suhu = dht.readTemperature();
    lembab = dht.readHumidity();

    if (mqtt.connected()) {
      StaticJsonDocument<256> doc;
      doc["suhu"] = isnan(suhu) ? 0 : suhu;
      doc["lembab"] = isnan(lembab) ? 0 : lembab;
      doc["watt"] = dayaWatt;
      doc["amper"] = arusRMS;
      doc["pintu"] = statusPintu ? "terbuka" : "tertutup";

      char buffer[256];
      serializeJson(doc, buffer);
      mqtt.publish(MQTT_TOPIC, buffer);
      
      Serial.printf("[MQTT] Sent -> A:%.2f, W:%.0f\n", arusRMS, dayaWatt);
    }
    lastMqttSend = now;
  }

  handleDisplayAndSecurity();
}