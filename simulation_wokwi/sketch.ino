/*
  sketch.ino – ESP32 AI-IoT Mini Flood Warning Station (Prototype V1)
  Đề tài: AI-IoT dự báo nguy cơ ngập cục bộ hố ga / rãnh thoát nước trường học (40 cm)
  Môi trường: Wokwi ESP32 Simulator & Phần cứng thực tế
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <time.h>

// --- PIN ASSIGNMENT (Khớp diagram.json) ---
#define PIN_TRIG 18
#define PIN_ECHO 19
#define PIN_RAIN_POT 34   // Giả lập tín hiệu cảm biến mưa (0 - 120 mm/h)
#define PIN_LED_GREEN 25  // Mức 0: An toàn
#define PIN_LED_YELLOW 26 // Mức 1: Có nguy cơ
#define PIN_LED_RED 27    // Mức 2: Nguy hiểm cao
#define PIN_BUZZER 32     // Còi cảnh báo

// LCD 1602 I2C
LiquidCrystal_I2C lcd(0x27, 16, 2);

// --- CẤU HÌNH TRẠM VÀ HẠ TẦNG ---
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";
const char* API_URL = "http://10.0.2.2:8000/api/v1/telemetry"; // Hoặc IP máy chủ FastAPI
const char* DEVICE_KEY = "change-me";
const char* DEVICE_ID = "mini-flood-station-01";

const float SENSOR_MOUNT_HEIGHT_CM = 40.0f; // Hố ga sâu 40 cm
const unsigned long SEND_INTERVAL_MS = 60000; // 1 phút / chu kỳ gửi
const int BUFFER_SIZE = 50;

// Ngưỡng an toàn V1 (Offline Fallback Rule)
const float THRESHOLD_WARN_CM = 15.0f;
const float THRESHOLD_DANGER_CM = 25.0f;
const float THRESHOLD_RAIN_WARN_MMH = 25.0f;
const float THRESHOLD_RAIN_DANGER_MMH = 40.0f;

struct TelemetryRecord {
  unsigned long sequenceNo;
  String timestamp;
  float rainIntervalMM;
  float rainRateMMH;
  float waterLevelCM;
  String qualityFlags;
};

TelemetryRecord pending[BUFFER_SIZE];
int queueHead = 0;
int queueCount = 0;
unsigned long lastMeasureAt = 0;
float prevWaterLevelCM = 0.0f;
Preferences preferences;

// --- HÀM ĐO ĐẠC CẢM BIẾN ---
float readDistanceCM(bool& valid) {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  unsigned long duration = pulseIn(PIN_ECHO, HIGH, 30000);
  valid = (duration > 0);
  if (!valid) return SENSOR_MOUNT_HEIGHT_CM;
  return duration * 0.0343f / 2.0f;
}

float readRainRateMMH() {
  int raw = analogRead(PIN_RAIN_POT);
  return (raw * 120.0f) / 4095.0f; // 0..120 mm/h
}

String isoTimestamp() {
  struct tm timeInfo;
  if (!getLocalTime(&timeInfo, 2000)) {
    return "2026-10-17T09:00:00+07:00";
  }
  char buffer[32];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%S+07:00", &timeInfo);
  return String(buffer);
}

// --- QUẢN LÝ BUFFER NGOẠI TUYẾN ---
void enqueueRecord(const TelemetryRecord& record) {
  if (queueCount == BUFFER_SIZE) {
    queueHead = (queueHead + 1) % BUFFER_SIZE;
    queueCount--;
  }
  int tail = (queueHead + queueCount) % BUFFER_SIZE;
  pending[tail] = record;
  queueCount++;
}

String toJson(const TelemetryRecord& record) {
  String json = "{";
  json += "\"schema_version\":1,";
  json += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  json += "\"sequence_no\":" + String(record.sequenceNo) + ",";
  json += "\"timestamp\":\"" + record.timestamp + "\",";
  json += "\"rain_interval_mm\":" + String(record.rainIntervalMM, 3) + ",";
  json += "\"rain_rate_mmh\":" + String(record.rainRateMMH, 2) + ",";
  json += "\"water_level_cm\":" + String(record.waterLevelCM, 2) + ",";
  json += "\"quality_flags\":" + record.qualityFlags;
  json += "}";
  return json;
}

// --- ĐIỀU KHIỂN CẢNH BÁO TẠI CHỖ (ACTUATORS) ---
void applyAlertLevel(int level, const char* source) {
  Serial.printf("[ALERT] Cap do: %d | Nguon: %s\n", level, source);

  if (level == 0) { // An toàn
    digitalWrite(PIN_LED_GREEN, HIGH);
    digitalWrite(PIN_LED_YELLOW, LOW);
    digitalWrite(PIN_LED_RED, LOW);
    noTone(PIN_BUZZER);
    lcd.setCursor(0, 1);
    lcd.print("[0: AN TOAN]     ");
  } else if (level == 1) { // Có nguy cơ
    digitalWrite(PIN_LED_GREEN, LOW);
    digitalWrite(PIN_LED_YELLOW, HIGH);
    digitalWrite(PIN_LED_RED, LOW);
    noTone(PIN_BUZZER);
    lcd.setCursor(0, 1);
    lcd.print("[1: NGUY CO]     ");
  } else { // Nguy hiểm cao
    digitalWrite(PIN_LED_GREEN, LOW);
    digitalWrite(PIN_LED_YELLOW, LOW);
    digitalWrite(PIN_LED_RED, HIGH);
    tone(PIN_BUZZER, 1000, 300); // Còi hú ngắt quãng
    lcd.setCursor(0, 1);
    lcd.print("[2: NGUY HIEM!]  ");
  }
}

// --- CÂY QUYẾT ĐỊNH THEO NGƯỠNG DỰ PHÒNG (OFFLINE RULE) ---
int evaluateOfflineSafetyRule(float waterLevelCM, float deltaRiseCM, float rainRateMMH) {
  // Nguy hiểm cao (Mức 2)
  if (waterLevelCM >= THRESHOLD_DANGER_CM || deltaRiseCM >= 6.0f ||
      (waterLevelCM >= 20.0f && rainRateMMH > THRESHOLD_RAIN_DANGER_MMH)) {
    return 2;
  }
  // Có nguy cơ (Mức 1)
  if (waterLevelCM >= THRESHOLD_WARN_CM || deltaRiseCM >= 3.0f || rainRateMMH >= THRESHOLD_RAIN_WARN_MMH) {
    return 1;
  }
  // An toàn (Mức 0)
  return 0;
}

// --- TRUYỀN DỮ LIỆU HTTP ---
bool postRecord(const TelemetryRecord& record, int& serverRiskLevel) {
  serverRiskLevel = -1;
  if (WiFi.status() != WL_CONNECTED) return false;

  HTTPClient http;
  http.setTimeout(4000);
  http.begin(API_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);

  int status = http.POST(toJson(record));
  if (status >= 200 && status < 300) {
    String payload = http.getString();
    http.end();
    StaticJsonDocument<1024> doc;
    DeserializationError err = deserializeJson(doc, payload);
    if (!err) {
      if (doc.containsKey("predictions") && !doc["predictions"].isNull()) {
        int r15 = doc["predictions"]["15m"]["risk_level"] | 0;
        int r30 = doc["predictions"]["30m"]["risk_level"] | 0;
        serverRiskLevel = max(r15, r30);
      } else if (doc["rule_override"] == true) {
        serverRiskLevel = 2;
      }
    }
    return true;
  }
  http.end();
  return false;
}

void flushQueue() {
  while (queueCount > 0 && WiFi.status() == WL_CONNECTED) {
    int dummyLevel = -1;
    if (!postRecord(pending[queueHead], dummyLevel)) break;
    queueHead = (queueHead + 1) % BUFFER_SIZE;
    queueCount--;
    delay(50);
  }
}

void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 3000) {
    delay(200);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_RAIN_POT, INPUT);
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_YELLOW, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);

  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("MINI FLOOD AI");
  lcd.setCursor(0, 1);
  lcd.print("SYSTEM INIT...");

  preferences.begin("mini-flood", false);
  ensureWiFi();
  configTime(7 * 3600, 0, "pool.ntp.org", "time.google.com");
  delay(1000);
  applyAlertLevel(0, "INIT");
}

void loop() {
  ensureWiFi();
  flushQueue();

  if (lastMeasureAt == 0 || millis() - lastMeasureAt >= SEND_INTERVAL_MS) {
    unsigned long elapsedMs = (lastMeasureAt == 0) ? SEND_INTERVAL_MS : (millis() - lastMeasureAt);
    lastMeasureAt = millis();

    bool distanceValid = false;
    float distanceCM = readDistanceCM(distanceValid);
    float waterLevelCM = max(0.0f, SENSOR_MOUNT_HEIGHT_CM - distanceCM);
    float rainRateMMH = readRainRateMMH();
    float deltaRiseCM = (prevWaterLevelCM > 0) ? (waterLevelCM - prevWaterLevelCM) : 0.0f;
    prevWaterLevelCM = waterLevelCM;

    float intervalHours = elapsedMs / 3600000.0f;
    unsigned long seq = preferences.getULong("sequence", 0) + 1;
    preferences.putULong("sequence", seq);

    // Cập nhật LCD dòng 1
    lcd.setCursor(0, 0);
    lcd.print("W:" + String((int)waterLevelCM) + "cm R:" + String((int)rainRateMMH) + "mm/h ");

    TelemetryRecord record;
    record.sequenceNo = seq;
    record.timestamp = isoTimestamp();
    record.rainRateMMH = rainRateMMH;
    record.rainIntervalMM = rainRateMMH * intervalHours;
    record.waterLevelCM = waterLevelCM;
    record.qualityFlags = distanceValid ? "[]" : "[\"water_sensor_timeout\"]";

    // 1. Luôn tính toán quy tắc an toàn offline tại chỗ
    int offlineLevel = evaluateOfflineSafetyRule(waterLevelCM, deltaRiseCM, rainRateMMH);

    // 2. Cố gắng gửi bản ghi lên server
    int serverLevel = -1;
    bool sentSuccess = postRecord(record, serverLevel);

    if (sentSuccess) {
      // Khi có kết quả từ AI, mức cảnh báo = max(AI, offlineRule) (safety-first)
      int finalLevel = (serverLevel >= 0) ? max(serverLevel, offlineLevel) : offlineLevel;
      applyAlertLevel(finalLevel, "SERVER_AI");
    } else {
      // Mất mạng: lưu đệm vào queue và kích hoạt cảnh báo an toàn dự phòng tại chỗ
      enqueueRecord(record);
      applyAlertLevel(offlineLevel, "OFFLINE_FALLBACK");
    }
  }

  delay(200);
}
