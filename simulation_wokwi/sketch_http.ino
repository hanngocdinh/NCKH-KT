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

#define PIN_TRIG 18
#define PIN_ECHO 19
#define PIN_RAIN_POT 34

const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";
const char* API_URL = "http://192.168.1.100:8000/api/v1/telemetry";
const char* DEVICE_KEY = "change-me";
const char* DEVICE_ID = "mini-flood-station-01";

const float SENSOR_MOUNT_HEIGHT_CM = 40.0;
const unsigned long SEND_INTERVAL_MS = 60000;
const int BUFFER_SIZE = 100;

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

float readDistanceCM(bool& valid) {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long duration = pulseIn(PIN_ECHO, HIGH, 30000);
  valid = duration > 0;
  return valid ? duration * 0.0343f / 2.0f : SENSOR_MOUNT_HEIGHT_CM;
}

float readRainRateMMH() {
  int raw = analogRead(PIN_RAIN_POT);
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
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  http.setTimeout(5000);
  http.begin(API_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);
  int status = http.POST(toJson(record));
  String response = http.getString();
  http.end();
  Serial.printf("HTTP %d %s\n", status, response.c_str());
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
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 8000) {
    delay(250);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_RAIN_POT, INPUT);
  preferences.begin("mini-flood", false);
  ensureWiFi();
  configTime(7 * 3600, 0, "pool.ntp.org", "time.google.com");
}

void loop() {
  ensureWiFi();
  flushQueue();

  if (lastMeasureAt == 0 || millis() - lastMeasureAt >= SEND_INTERVAL_MS) {
    unsigned long elapsedMs = lastMeasureAt == 0 ? SEND_INTERVAL_MS : millis() - lastMeasureAt;
    lastMeasureAt = millis();

    bool distanceValid = false;
    float distanceCM = readDistanceCM(distanceValid);
    float waterLevelCM = max(0.0f, SENSOR_MOUNT_HEIGHT_CM - distanceCM);
    float rainRateMMH = readRainRateMMH();
    float intervalHours = elapsedMs / 3600000.0f;

    unsigned long sequenceNo = preferences.getULong("sequence", 0) + 1;
    preferences.putULong("sequence", sequenceNo);

    TelemetryRecord record;
    record.sequenceNo = sequenceNo;
    record.timestamp = isoTimestamp();
    record.rainRateMMH = rainRateMMH;
    record.rainIntervalMM = rainRateMMH * intervalHours;
    record.waterLevelCM = waterLevelCM;
    record.qualityFlags = distanceValid ? "[]" : "[\"water_sensor_timeout\"]";
    enqueueRecord(record);
    flushQueue();
  }
  delay(250);
}
