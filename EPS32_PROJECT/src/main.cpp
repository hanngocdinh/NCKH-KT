#include <Arduino.h>

/*
  ESP32 HTTP telemetry cho prototype mô hình mini.
  Wokwi dùng biến trở làm cảm biến mưa và HC-SR04 làm cảm biến mực nước.
  Khi chạy trên phần cứng thật, thay readRainRateMMH() bằng driver Modbus
  theo đúng datasheet của cảm biến mưa RS485.
*/

#include <HTTPClient.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <time.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
// Cau hinh an toan de build/mo phong khi chua tao include/secrets.h.
#define MINI_FLOOD_WIFI_SSID "Wokwi-GUEST"
#define MINI_FLOOD_WIFI_PASSWORD ""
#define MINI_FLOOD_API_URL "http://host.wokwi.internal:8000/api/v2/telemetry"
#define MINI_FLOOD_DEVICE_KEY "change-me"
#endif

#define PIN_TRIG_WATER 18
#define PIN_ECHO_WATER 19
#define PIN_TRIG_RAIN 5
#define PIN_ECHO_RAIN 17
#define PIN_RAIN_POT 34
// LED D2 tren bo: trang thai tong hop.
#define PIN_STATUS_LED 2
// Bon LED ngoai, moi LED noi tu GPIO qua dien tro 220-330 ohm den GND.
#define PIN_LED_WIFI 25
#define PIN_LED_BACKEND 26
#define PIN_LED_WATER 27
#define PIN_LED_RAIN 33

const char *WIFI_SSID = MINI_FLOOD_WIFI_SSID;
const char *WIFI_PASSWORD = MINI_FLOOD_WIFI_PASSWORD;
const char *API_URL = MINI_FLOOD_API_URL;
const char *DEVICE_KEY = MINI_FLOOD_DEVICE_KEY;
const char *DEVICE_ID = "mini-flood-station-01";

// Khoảng cách từ đầu dò xuống đáy để đổi khoảng cách siêu âm thành
// water_level_cm. Đây KHÔNG phải ngưỡng tràn; ngưỡng tràn được cấu hình động ở
// backend/dashboard.
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
bool backendConnected = false;
bool waterSensorConnected = false;
bool rainSensorVerified = false;
String rainSensorMode = "not_checked";
int lastHttpStatus = 0;
unsigned long lastBackendOkAt = 0;
WebServer healthServer(80);

String jsonBool(bool value) { return value ? "true" : "false"; }

String healthJson() {
  bool wifiConnected = WiFi.status() == WL_CONNECTED;
  bool overallOk = wifiConnected && backendConnected &&
                   waterSensorConnected && rainSensorVerified;
  String json = "{";
  json += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  json += "\"overall\":\"" + String(overallOk ? "ok" : "degraded") + "\",";
  json += "\"wifi\":{";
  json += "\"connected\":" + jsonBool(wifiConnected) + ",";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  json += "\"rssi_dbm\":" + String(wifiConnected ? WiFi.RSSI() : 0);
  json += "},";
  json += "\"backend\":{";
  json += "\"connected\":" + jsonBool(backendConnected) + ",";
  json += "\"last_http_status\":" + String(lastHttpStatus) + ",";
  json += "\"last_ok_ms\":" + String(lastBackendOkAt);
  json += "},";
  json += "\"water_sensor\":{";
  json += "\"connected\":" + jsonBool(waterSensorConnected) + ",";
  json += "\"check\":\"hc_sr04_echo\"";
  json += "},";
  json += "\"rain_sensor\":{";
  json += "\"verified\":" + jsonBool(rainSensorVerified) + ",";
  json += "\"mode\":\"" + rainSensorMode + "\"";
  json += "},";
  json += "\"rs485\":{";
  json += "\"configured\":false,";
  json += "\"connected\":false,";
  json += "\"reason\":\"missing_modbus_register_map\"";
  json += "},";
  json += "\"queue_count\":" + String(queueCount) + ",";
  json += "\"uptime_ms\":" + String(millis());
  json += "}";
  return json;
}

void printHealth() {
  Serial.printf(
      "[HEALTH] wifi=%s backend=%s(http=%d) water=%s rain=%s rs485=NOT_CONFIGURED\n",
      WiFi.status() == WL_CONNECTED ? "OK" : "FAIL",
      backendConnected ? "OK" : "FAIL", lastHttpStatus,
      waterSensorConnected ? "OK" : "FAIL", rainSensorMode.c_str());
}

void updateStatusLeds() {
  bool wifiConnected = WiFi.status() == WL_CONNECTED;
  digitalWrite(PIN_LED_WIFI, wifiConnected ? HIGH : LOW);
  digitalWrite(PIN_LED_BACKEND, backendConnected ? HIGH : LOW);
  digitalWrite(PIN_LED_WATER, waterSensorConnected ? HIGH : LOW);
  digitalWrite(PIN_LED_RAIN, rainSensorVerified ? HIGH : LOW);

  // D2 sang lien tuc khi tat ca cum dang san sang.
  if (wifiConnected && backendConnected && waterSensorConnected &&
      rainSensorVerified) {
    digitalWrite(PIN_STATUS_LED, HIGH);
    return;
  }

  unsigned long phase = millis() % 1500;
  if (!wifiConnected || !backendConnected) {
    // Mot chop cham: loi duong truyen Wi-Fi/backend.
    digitalWrite(PIN_STATUS_LED, phase < 250 ? HIGH : LOW);
  } else {
    // Hai chop nhanh: Wi-Fi/backend OK nhung co cam bien loi.
    bool doubleBlink = phase < 120 || (phase >= 260 && phase < 380);
    digitalWrite(PIN_STATUS_LED, doubleBlink ? HIGH : LOW);
  }
}

void setBackendLed(bool connected) {
  backendConnected = connected;
  digitalWrite(PIN_LED_BACKEND, connected ? HIGH : LOW);
}

float readEchoDistance(uint8_t trigPin, uint8_t echoPin, bool &valid,
                       float defaultDistance) {
  // Ping ba lan. Can it nhat hai Echo hop le de tranh bao OK do xung nhieu.
  const int attempts = 3;
  float distanceTotal = 0.0f;
  int validCount = 0;
  for (int attempt = 0; attempt < attempts; attempt++) {
    digitalWrite(trigPin, LOW);
    delayMicroseconds(3);
    digitalWrite(trigPin, HIGH);
    delayMicroseconds(10);
    digitalWrite(trigPin, LOW);

    unsigned long duration = pulseIn(echoPin, HIGH, 30000);
    float distance = duration * 0.0343f / 2.0f;
    if (duration > 0 && distance >= 2.0f && distance <= 400.0f) {
      distanceTotal += distance;
      validCount++;
    }
    // HC-SR04 can khoang cach giua hai lan phat de tranh Echo cheo.
    delay(60);
  }
  valid = validCount >= 2;
  return valid ? distanceTotal / validCount : defaultDistance;
}

float readRainRateMMH(bool &rainSensorValid) {
  // Ưu tiên đọc Cảm biến Siêu âm 2 (mô phỏng mực nước ống hứng mưa)
  bool ultrasonicRainValid = false;
  float dist = readEchoDistance(PIN_TRIG_RAIN, PIN_ECHO_RAIN,
                                ultrasonicRainValid, RAIN_GAUGE_HEIGHT_CM);
  if (ultrasonicRainValid) {
    rainSensorValid = true;
    rainSensorVerified = true;
    rainSensorMode = "hc_sr04_echo_ok";
    // Khoảng cách 30cm -> 0 mm/h (ống cạn, không mưa); Khoảng cách 5cm -> 100
    // mm/h (mưa rất to)
    float rainHeight = max(0.0f, RAIN_GAUGE_HEIGHT_CM - dist);
    return rainHeight * 4.0f; // 25cm nước dâng = 100 mm/h
  }

  // Fallback sang biến trở analog nếu cảm biến siêu âm 2 không có tín hiệu
  int raw = analogRead(PIN_RAIN_POT);
  rainSensorValid = true;
  // analogRead() vẫn trả số khi chân bị thả nổi, nên không thể dùng nó để xác
  // nhận cảm biến thật đang kết nối. Giá trị vẫn được gửi để tương thích mô
  // phỏng, nhưng health/quality phải báo chưa được xác minh.
  rainSensorVerified = false;
  rainSensorMode = "analog_fallback_unverified";
  return raw * 120.0f / 4095.0f;
}

String buildQualityFlags(bool waterValid) {
  String flags = "[";
  bool hasFlag = false;
  if (!waterValid) {
    flags += "\"water_sensor_timeout\"";
    hasFlag = true;
  }
  if (!rainSensorVerified) {
    if (hasFlag)
      flags += ",";
    flags += "\"rain_sensor_unverified\"";
  }
  flags += "]";
  return flags;
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

void enqueueRecord(const TelemetryRecord &record) {
  if (queueCount == BUFFER_SIZE) {
    queueHead = (queueHead + 1) % BUFFER_SIZE;
    queueCount--;
  }
  int tail = (queueHead + queueCount) % BUFFER_SIZE;
  pending[tail] = record;
  queueCount++;
}

String toJson(const TelemetryRecord &record) {
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

bool postRecord(const TelemetryRecord &record) {
  if (WiFi.status() != WL_CONNECTED) {
    setBackendLed(false);
    Serial.printf("[HTTP] Bo qua seq=%lu: Wi-Fi chua ket noi\n",
                  record.sequenceNo);
    return false;
  }

  String payload = toJson(record);
  HTTPClient http;
  http.setTimeout(5000);
  if (!http.begin(API_URL)) {
    setBackendLed(false);
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
    Serial.printf("[HTTP] Loi ket noi %d: %s\n", status,
                  HTTPClient::errorToString(status).c_str());
  } else {
    Serial.printf("[HTTP] Phan hoi %d: %s\n", status, response.c_str());
  }
  bool accepted = status >= 200 && status < 300;
  lastHttpStatus = status;
  if (accepted)
    lastBackendOkAt = millis();
  setBackendLed(accepted);
  return accepted;
}

void flushQueue() {
  while (queueCount > 0 && WiFi.status() == WL_CONNECTED) {
    if (!postRecord(pending[queueHead]))
      break;
    queueHead = (queueHead + 1) % BUFFER_SIZE;
    queueCount--;
    delay(100);
  }
}

void diagnoseWiFiNetwork() {
  Serial.printf("[WiFi] Dang quet mang 2.4GHz de tim %s...\n", WIFI_SSID);
  int networkCount = WiFi.scanNetworks(false, true);
  bool found = false;
  for (int i = 0; i < networkCount; i++) {
    if (WiFi.SSID(i) == WIFI_SSID) {
      found = true;
      Serial.printf("[WiFi] Tim thay %s: channel=%d RSSI=%ddBm\n", WIFI_SSID,
                    WiFi.channel(i), WiFi.RSSI(i));
    }
  }
  if (!found) {
    Serial.printf("[WiFi] KHONG tim thay %s tren bang tan 2.4GHz\n", WIFI_SSID);
  }
  WiFi.scanDelete();
}

void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED)
    return;
  setBackendLed(false);
  Serial.printf("[WiFi] Dang ket noi %s", WIFI_SSID);
  WiFi.disconnect(false, false);
  delay(100);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 8000) {
    // Nhấp nháy D2 trong lúc đang kết nối Wi-Fi.
    digitalWrite(PIN_STATUS_LED, !digitalRead(PIN_STATUS_LED));
    Serial.print(".");
    delay(250);
  }
  digitalWrite(PIN_STATUS_LED, LOW);
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WiFi] Da ket noi, IP=%s\n",
                  WiFi.localIP().toString().c_str());
    Serial.printf("[HEALTH] Mo tren trinh duyet: http://%s/health\n",
                  WiFi.localIP().toString().c_str());
  } else {
    Serial.printf("\n[WiFi] That bai, status=%d; se thu lai\n", WiFi.status());
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  pinMode(PIN_STATUS_LED, OUTPUT);
  pinMode(PIN_LED_WIFI, OUTPUT);
  pinMode(PIN_LED_BACKEND, OUTPUT);
  pinMode(PIN_LED_WATER, OUTPUT);
  pinMode(PIN_LED_RAIN, OUTPUT);
  digitalWrite(PIN_LED_WIFI, LOW);
  digitalWrite(PIN_LED_BACKEND, LOW);
  digitalWrite(PIN_LED_WATER, LOW);
  digitalWrite(PIN_LED_RAIN, LOW);
  setBackendLed(false);
  Serial.println("\n[BOOT] Mini Flood firmware V2 signal-first");
  Serial.printf("[BOOT] Device: %s\n", DEVICE_ID);
  char bootIdBuffer[18];
  snprintf(bootIdBuffer, sizeof(bootIdBuffer), "%08lx-%08lx",
           (unsigned long)esp_random(), (unsigned long)esp_random());
  bootId = String(bootIdBuffer);
  Serial.printf("[BOOT] Session: %s\n", bootId.c_str());
  Serial.printf("[BOOT] API: %s\n", API_URL);
  pinMode(PIN_TRIG_WATER, OUTPUT);
  pinMode(PIN_ECHO_WATER, INPUT);
  pinMode(PIN_TRIG_RAIN, OUTPUT);
  pinMode(PIN_ECHO_RAIN, INPUT);
  pinMode(PIN_RAIN_POT, INPUT);
  preferences.begin("mini-flood", false);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  healthServer.on("/", HTTP_GET, []() {
    healthServer.sendHeader("Location", "/health", true);
    healthServer.send(302, "text/plain", "Open /health");
  });
  healthServer.on("/health", HTTP_GET, []() {
    healthServer.send(200, "application/json; charset=utf-8", healthJson());
  });
  healthServer.onNotFound([]() {
    healthServer.send(404, "application/json", "{\"error\":\"not_found\"}");
  });
  healthServer.begin();
  Serial.println("[HEALTH] Local health server da san sang tai cong 80");
  diagnoseWiFiNetwork();
  configTime(7 * 3600, 0, "pool.ntp.org", "time.google.com");
}

void loop() {
  // Luôn lấy mẫu trước khi thử kết nối mạng. Nhờ vậy cảm biến vẫn hoạt động
  // và có log [SENSOR] ngay cả khi Wi-Fi/backend đang mất kết nối.
  if (lastMeasureAt == 0 || millis() - lastMeasureAt >= SEND_INTERVAL_MS) {
    unsigned long elapsedMs =
        lastMeasureAt == 0 ? SEND_INTERVAL_MS : millis() - lastMeasureAt;
    lastMeasureAt = millis();

    // 1. Cảm biến siêu âm 1: Mực nước hố ga
    bool waterValid = false;
    float waterDistCM = readEchoDistance(PIN_TRIG_WATER, PIN_ECHO_WATER,
                                         waterValid, SENSOR_MOUNT_HEIGHT_CM);
    float waterLevelCM = max(0.0f, SENSOR_MOUNT_HEIGHT_CM - waterDistCM);
    waterSensorConnected = waterValid;

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
    record.qualityFlags = buildQualityFlags(waterValid);
    enqueueRecord(record);
    Serial.printf("[SENSOR] seq=%lu water=%.2fcm rain=%.2fmm/h queue=%d\n",
                  sequenceNo, waterLevelCM, rainRateMMH, queueCount);
    printHealth();
  }

  ensureWiFi();
  flushQueue();
  healthServer.handleClient();
  updateStatusLeds();
  delay(250);
}
