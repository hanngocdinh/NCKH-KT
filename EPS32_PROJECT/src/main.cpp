#include <Arduino.h>

/*
  ESP32 HTTP telemetry cho prototype mô hình mini.
  Wokwi dùng biến trở làm cảm biến mưa và HC-SR04 làm cảm biến mực nước.
  Khi chạy trên phần cứng thật, thay readRainRateMMH() bằng driver Modbus
  theo đúng datasheet của cảm biến mưa RS485.
*/

#include <HTTPClient.h>
#include <Preferences.h>
#include <WiFi.h>
#include <time.h>

#define PIN_TRIG_WATER 18
#define PIN_ECHO_WATER 19
#define PIN_TRIG_RAIN 5
#define PIN_ECHO_RAIN 17
#define PIN_RAIN_POT 34

const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";
// Khi mô phỏng bằng Wokwi Extension trên VS Code:
const char* API_URL = "http://host.wokwi.internal:8000/api/v2/telemetry";
// Khi nạp vào ESP32 mạch thật cùng mạng LAN: thay bằng IP máy tính (vd: "http://192.168.1.17:8000/api/v2/telemetry")
const char* DEVICE_KEY = "change-me";
const char* DEVICE_ID = "mini-flood-station-01";

// Khoảng cách từ đầu dò xuống đáy để đổi khoảng cách siêu âm thành water_level_cm.
// Đây KHÔNG phải ngưỡng tràn; ngưỡng tràn được cấu hình động ở backend/dashboard.
const float SENSOR_MOUNT_HEIGHT_CM = 40.0;
const float RAIN_GAUGE_HEIGHT_CM = 30.0;
// Test nhanh: 5 giây/lần. Khi nạp mạch thật: đổi lại thành 60000
const unsigned long SEND_INTERVAL_MS = 5000;
const int BUFFER_SIZE = 100;
String bootId;

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
Preferences preferences;

float readEchoDistance(uint8_t trigPin, uint8_t echoPin, bool& valid, float defaultDistance) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  unsigned long duration = pulseIn(echoPin, HIGH, 30000);
  valid = duration > 0;
  return valid ? duration * 0.0343f / 2.0f : defaultDistance;
}

float readRainRateMMH(bool& rainSensorValid) {
  // Ưu tiên đọc Cảm biến Siêu âm 2 (mô phỏng mực nước ống hứng mưa)
  bool ultrasonicRainValid = false;
  float dist = readEchoDistance(PIN_TRIG_RAIN, PIN_ECHO_RAIN, ultrasonicRainValid, RAIN_GAUGE_HEIGHT_CM);
  if (ultrasonicRainValid && dist <= RAIN_GAUGE_HEIGHT_CM) {
    rainSensorValid = true;
    // Khoảng cách 30cm -> 0 mm/h (ống cạn, không mưa); Khoảng cách 5cm -> 100 mm/h (mưa rất to)
    float rainHeight = max(0.0f, RAIN_GAUGE_HEIGHT_CM - dist);
    return rainHeight * 4.0f; // 25cm nước dâng = 100 mm/h
  }

  // Fallback sang biến trở analog nếu cảm biến siêu âm 2 không có tín hiệu
  int raw = analogRead(PIN_RAIN_POT);
  rainSensorValid = true;
  return raw * 120.0f / 4095.0f;
}

String isoTimestamp() {
  struct tm timeInfo;
  if (!getLocalTime(&timeInfo, 2000)) {
    return "1970-01-01T00:00:00+00:00";
  }
  char buffer[32];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%S+07:00", &timeInfo);
  return String(buffer);
}

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
  json += "\"boot_id\":\"" + bootId + "\",";
  json += "\"sequence_no\":" + String(record.sequenceNo) + ",";
  json += "\"timestamp\":\"" + record.timestamp + "\",";
  json += "\"rain_interval_mm\":" + String(record.rainIntervalMM, 3) + ",";
  json += "\"rain_rate_mmh\":" + String(record.rainRateMMH, 2) + ",";
  json += "\"water_level_cm\":" + String(record.waterLevelCM, 2) + ",";
  json += "\"quality_flags\":" + record.qualityFlags;
  json += "}";
  return json;
}

bool postRecord(const TelemetryRecord& record) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.printf("[HTTP] Bo qua seq=%lu: Wi-Fi chua ket noi\n", record.sequenceNo);
    return false;
  }

  String payload = toJson(record);
  HTTPClient http;
  http.setTimeout(5000);
  if (!http.begin(API_URL)) {
    Serial.printf("[HTTP] Khong the khoi tao URL: %s\n", API_URL);
    return false;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);
  Serial.printf("[HTTP] POST seq=%lu -> %s\n", record.sequenceNo, API_URL);
  Serial.printf("[HTTP] Payload: %s\n", payload.c_str());
  int status = http.POST(payload);
  String response = http.getString();
  http.end();
  if (status < 0) {
    Serial.printf("[HTTP] Loi ket noi %d: %s\n", status, HTTPClient::errorToString(status).c_str());
  } else {
    Serial.printf("[HTTP] Phan hoi %d: %s\n", status, response.c_str());
  }
  return status >= 200 && status < 300;
}

void flushQueue() {
  while (queueCount > 0 && WiFi.status() == WL_CONNECTED) {
    if (!postRecord(pending[queueHead])) break;
    queueHead = (queueHead + 1) % BUFFER_SIZE;
    queueCount--;
    delay(100);
  }
}

void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.printf("[WiFi] Dang ket noi %s", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 8000) {
    Serial.print(".");
    delay(250);
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WiFi] Da ket noi, IP=%s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.printf("\n[WiFi] That bai, status=%d; se thu lai\n", WiFi.status());
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n[BOOT] Mini Flood firmware V2 signal-first");
  Serial.printf("[BOOT] Device: %s\n", DEVICE_ID);
  char bootIdBuffer[18];
  snprintf(
    bootIdBuffer,
    sizeof(bootIdBuffer),
    "%08lx-%08lx",
    (unsigned long)esp_random(),
    (unsigned long)esp_random()
  );
  bootId = String(bootIdBuffer);
  Serial.printf("[BOOT] Session: %s\n", bootId.c_str());
  Serial.printf("[BOOT] API: %s\n", API_URL);
  pinMode(PIN_TRIG_WATER, OUTPUT);
  pinMode(PIN_ECHO_WATER, INPUT);
  pinMode(PIN_TRIG_RAIN, OUTPUT);
  pinMode(PIN_ECHO_RAIN, INPUT);
  pinMode(PIN_RAIN_POT, INPUT);
  preferences.begin("mini-flood", false);
  configTime(7 * 3600, 0, "pool.ntp.org", "time.google.com");
}

void loop() {
  // Luôn lấy mẫu trước khi thử kết nối mạng. Nhờ vậy cảm biến vẫn hoạt động
  // và có log [SENSOR] ngay cả khi Wi-Fi/backend đang mất kết nối.
  if (lastMeasureAt == 0 || millis() - lastMeasureAt >= SEND_INTERVAL_MS) {
    unsigned long elapsedMs = lastMeasureAt == 0 ? SEND_INTERVAL_MS : millis() - lastMeasureAt;
    lastMeasureAt = millis();

    // 1. Cảm biến siêu âm 1: Mực nước hố ga
    bool waterValid = false;
    float waterDistCM = readEchoDistance(PIN_TRIG_WATER, PIN_ECHO_WATER, waterValid, SENSOR_MOUNT_HEIGHT_CM);
    float waterLevelCM = max(0.0f, SENSOR_MOUNT_HEIGHT_CM - waterDistCM);

    // 2. Cảm biến siêu âm 2 (hoặc biến trở): Cường độ mưa
    bool rainValid = false;
    float rainRateMMH = readRainRateMMH(rainValid);
    float intervalHours = elapsedMs / 3600000.0f;

    unsigned long sequenceNo = preferences.getULong("sequence", 0) + 1;
    preferences.putULong("sequence", sequenceNo);

    TelemetryRecord record;
    record.sequenceNo = sequenceNo;
    record.timestamp = isoTimestamp();
    record.rainRateMMH = rainRateMMH;
    record.rainIntervalMM = rainRateMMH * intervalHours;
    record.waterLevelCM = waterLevelCM;
    record.qualityFlags = waterValid ? "[]" : "[\"water_sensor_timeout\"]";
    enqueueRecord(record);
    Serial.printf(
      "[SENSOR] seq=%lu water=%.2fcm rain=%.2fmm/h queue=%d\n",
      sequenceNo,
      waterLevelCM,
      rainRateMMH,
      queueCount
    );
  }

  ensureWiFi();
  flushQueue();
  delay(250);
}
