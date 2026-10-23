#include <Arduino.h>

#if defined(MINI_FLOOD_PROFILE_SIMULATION) && defined(MINI_FLOOD_PROFILE_REAL_HARDWARE)
#error "Chi duoc chon mot profile firmware"
#endif
#if !defined(MINI_FLOOD_PROFILE_SIMULATION) && !defined(MINI_FLOOD_PROFILE_REAL_HARDWARE)
#define MINI_FLOOD_PROFILE_SIMULATION 1
#endif

/*
  ESP32 HTTP telemetry cho prototype mô hình mini.
  - profile simulation: HC-SR04 + bien tro trong Wokwi.
  - profile real_hardware: HC-SR04 GPIO18/19 + Modbus RTU GPIO16/17.
*/

#include <HTTPClient.h>
#if defined(MINI_FLOOD_PROFILE_REAL_HARDWARE)
#include <ESPmDNS.h>
#endif
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
#define MINI_FLOOD_BACKEND_MDNS_HOST "mini-flood-backend"
#define MINI_FLOOD_BACKEND_MDNS_PORT 8000
#define MINI_FLOOD_DEVICE_KEY "change-me"
#endif

#if defined(MINI_FLOOD_PROFILE_REAL_HARDWARE)
#if __has_include("hardware_config.h")
#include "hardware_config.h"
#else
// Cau hinh an toan: build duoc nhung khong gia dinh calibration/register.
#define MINI_FLOOD_WATER_CALIBRATED 0
#define MINI_FLOOD_WATER_SENSOR_HCSR04 1
#define MINI_FLOOD_WATER_HCSR04_TRIG_PIN 18
#define MINI_FLOOD_WATER_HCSR04_ECHO_PIN 19
#define MINI_FLOOD_WATER_ADC_DRY 0
#define MINI_FLOOD_WATER_ADC_FULL 3000
#define MINI_FLOOD_WATER_SENSOR_RANGE_CM 4.0f
#define MINI_FLOOD_WATER_ADC_INVERTED 0
#define MINI_FLOOD_RS485_PROBE_ENABLED 1
#define MINI_FLOOD_RS485_PROBE_FUNCTION 0x03
#define MINI_FLOOD_RS485_PROBE_REGISTER 0x0000
#define MINI_FLOOD_RS485_AUTO_DISCOVERY_ENABLED 1
#define MINI_FLOOD_RS485_DISCOVERY_RETRY_MS 60000UL
#define MINI_FLOOD_RAIN_MODBUS_CONFIGURED 0
#define MINI_FLOOD_RAIN_MODBUS_BAUD 4800
#define MINI_FLOOD_RAIN_MODBUS_SERIAL_CONFIG SERIAL_8N1
#define MINI_FLOOD_RAIN_MODBUS_SLAVE_ID 1
#define MINI_FLOOD_RAIN_MODBUS_FUNCTION 0x03
#define MINI_FLOOD_RAIN_MODBUS_REGISTER 0x0000
#define MINI_FLOOD_RAIN_MODBUS_SCALE 0.1f
#define MINI_FLOOD_RAIN_VALUE_MODE 1
#define MINI_FLOOD_RAIN_MAX_RATE_MMH 500.0f
#endif
#endif

#if defined(MINI_FLOOD_PROFILE_SIMULATION)
#define PIN_TRIG_WATER 18
#define PIN_ECHO_WATER 19
#define PIN_TRIG_RAIN 5
#define PIN_ECHO_RAIN 17
#define PIN_RAIN_POT 34
#else
#define PIN_WATER_ANALOG 34
#define PIN_TRIG_WATER MINI_FLOOD_WATER_HCSR04_TRIG_PIN
#define PIN_ECHO_WATER MINI_FLOOD_WATER_HCSR04_ECHO_PIN
#define PIN_RS485_RX 16
#define PIN_RS485_TX 17
#endif
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
#if defined(MINI_FLOOD_PROFILE_REAL_HARDWARE)
const char *BACKEND_MDNS_HOST = MINI_FLOOD_BACKEND_MDNS_HOST;
const uint16_t BACKEND_MDNS_PORT = MINI_FLOOD_BACKEND_MDNS_PORT;
#endif
#if defined(MINI_FLOOD_PROFILE_SIMULATION)
const char *HARDWARE_PROFILE = "simulation";
#else
const char *HARDWARE_PROFILE = "real_hardware";
#endif

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
int lastWaterAdcRaw = -1;
float lastWaterLevelCM = 0.0f;
float lastWaterDistanceCM = -1.0f;
unsigned long lastRainResponseMs = 0;
#if defined(MINI_FLOOD_PROFILE_REAL_HARDWARE)
bool rs485Connected = false;
uint8_t lastRs485Exception = 0;
size_t lastRs485ResponseBytes = 0;
uint32_t activeRainBaud = MINI_FLOOD_RAIN_MODBUS_BAUD;
uint8_t activeRainSlaveId = MINI_FLOOD_RAIN_MODBUS_SLAVE_ID;
bool rainModbusDiscovered = false;
unsigned long lastRs485DiscoveryAt = 0;
bool lastRainTotalValid = false;
float lastRainTotalMM = 0.0f;
#endif
int lastHttpStatus = 0;
unsigned long lastBackendOkAt = 0;
WebServer healthServer(80);
#if defined(MINI_FLOOD_PROFILE_REAL_HARDWARE)
String activeApiUrl;
bool mdnsStarted = false;
unsigned long lastBackendDiscoveryAt = 0;
const unsigned long BACKEND_DISCOVERY_RETRY_MS = 30000;
#endif

String jsonBool(bool value) { return value ? "true" : "false"; }

#if defined(MINI_FLOOD_PROFILE_REAL_HARDWARE)
bool discoverBackend(bool force = false) {
  if (WiFi.status() != WL_CONNECTED)
    return false;

  unsigned long now = millis();
  if (!force && lastBackendDiscoveryAt != 0 &&
      now - lastBackendDiscoveryAt < BACKEND_DISCOVERY_RETRY_MS) {
    return activeApiUrl.length() > 0;
  }
  lastBackendDiscoveryAt = now;

  if (!mdnsStarted) {
    mdnsStarted = MDNS.begin(DEVICE_ID);
    if (!mdnsStarted) {
      Serial.println("[mDNS] Khong the khoi tao mDNS client");
    }
  }

  if (mdnsStarted) {
    Serial.printf("[mDNS] Dang tim dich vu _mini-flood._tcp.local (%s.local)\n",
                  BACKEND_MDNS_HOST);
    int count = MDNS.queryService("mini-flood", "tcp");
    for (int index = 0; index < count; index++) {
      String discoveredHost = MDNS.hostname(index);
      IPAddress address = MDNS.IP(index);
      uint16_t port = MDNS.port(index);
      if (address == IPAddress(0, 0, 0, 0))
        continue;
      if (port == 0)
        port = BACKEND_MDNS_PORT;

      // Mang demo chi quang ba mot service mini-flood. Neu co nhieu service,
      // uu tien server co hostname da cau hinh.
      if (count > 1 && discoveredHost.indexOf(BACKEND_MDNS_HOST) < 0)
        continue;

      activeApiUrl = "http://" + address.toString() + ":" + String(port) +
                     "/api/v2/telemetry";
      preferences.putString("backend_url", activeApiUrl);
      Serial.printf("[mDNS] Backend: %s.local -> %s\n", BACKEND_MDNS_HOST,
                    activeApiUrl.c_str());
      return true;
    }
  }

  // Cache chi la fallback tam thoi. Sau loi HTTP firmware se tim mDNS lai.
  if (activeApiUrl.length() == 0) {
    activeApiUrl = preferences.getString("backend_url", "");
    if (activeApiUrl.length() > 0) {
      Serial.printf("[mDNS] Khong tim thay service, thu URL da luu: %s\n",
                    activeApiUrl.c_str());
    }
  }
  return activeApiUrl.length() > 0;
}
#endif

String healthJson() {
  bool wifiConnected = WiFi.status() == WL_CONNECTED;
  bool overallOk = wifiConnected && backendConnected &&
                   waterSensorConnected && rainSensorVerified;
  String json = "{";
  json += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  json += "\"hardware_profile\":\"" + String(HARDWARE_PROFILE) + "\",";
  json += "\"overall\":\"" + String(overallOk ? "ok" : "degraded") + "\",";
  json += "\"wifi\":{";
  json += "\"connected\":" + jsonBool(wifiConnected) + ",";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  json += "\"rssi_dbm\":" + String(wifiConnected ? WiFi.RSSI() : 0);
  json += "},";
  json += "\"backend\":{";
  json += "\"connected\":" + jsonBool(backendConnected) + ",";
  json += "\"last_http_status\":" + String(lastHttpStatus) + ",";
  json += "\"last_ok_ms\":" + String(lastBackendOkAt) + ",";
#if defined(MINI_FLOOD_PROFILE_REAL_HARDWARE)
  json += "\"discovery\":\"mdns\",";
  json += "\"host\":\"" + String(BACKEND_MDNS_HOST) + ".local\",";
  json += "\"url\":\"" + activeApiUrl + "\"";
#else
  json += "\"discovery\":\"static\",";
  json += "\"url\":\"" + String(API_URL) + "\"";
#endif
  json += "},";
  json += "\"water_sensor\":{";
  json += "\"connected\":" + jsonBool(waterSensorConnected) + ",";
#if defined(MINI_FLOOD_PROFILE_SIMULATION)
  json += "\"check\":\"hc_sr04_echo\"";
#else
#if MINI_FLOOD_WATER_SENSOR_HCSR04
  json += "\"check\":\"hc_sr04_echo\",";
  json += "\"trig_gpio\":" + String(PIN_TRIG_WATER) + ",";
  json += "\"echo_gpio\":" + String(PIN_ECHO_WATER) + ",";
  json += "\"distance_cm\":" + String(lastWaterDistanceCM, 2) + ",";
#else
  json += "\"check\":\"analog_adc_calibration\",";
  json += "\"calibrated\":" + jsonBool(MINI_FLOOD_WATER_CALIBRATED != 0) + ",";
  json += "\"adc_raw\":" + String(lastWaterAdcRaw) + ",";
#endif
  json += "\"level_cm\":" + String(lastWaterLevelCM, 2);
#endif
  json += "},";
  json += "\"rain_sensor\":{";
  json += "\"verified\":" + jsonBool(rainSensorVerified) + ",";
  json += "\"mode\":\"" + rainSensorMode + "\"";
  json += "},";
  json += "\"rs485\":{";
#if defined(MINI_FLOOD_PROFILE_SIMULATION)
  json += "\"configured\":false,";
  json += "\"connected\":false,";
  json += "\"reason\":\"simulation_profile\"";
#else
  json += "\"configured\":" + jsonBool(MINI_FLOOD_RAIN_MODBUS_CONFIGURED != 0) + ",";
  json += "\"probe_enabled\":" + jsonBool(MINI_FLOOD_RS485_PROBE_ENABLED != 0) + ",";
  json += "\"auto_discovery_enabled\":" + jsonBool(MINI_FLOOD_RS485_AUTO_DISCOVERY_ENABLED != 0) + ",";
  json += "\"discovered\":" + jsonBool(rainModbusDiscovered) + ",";
  json += "\"baud\":" + String(activeRainBaud) + ",";
  json += "\"slave_id\":" + String(activeRainSlaveId) + ",";
  json += "\"connected\":" + jsonBool(rs485Connected) + ",";
  json += "\"last_response_ms\":" + String(lastRainResponseMs) + ",";
  json += "\"last_response_bytes\":" + String(lastRs485ResponseBytes) + ",";
  json += "\"last_exception\":" + String(lastRs485Exception) + ",";
  String rs485Reason;
  if (MINI_FLOOD_RAIN_MODBUS_CONFIGURED)
    rs485Reason = rainSensorVerified ? "measurement_ok" : "measurement_failed";
  else if (rs485Connected)
    rs485Reason = lastRs485Exception ? "probe_exception_response" : "probe_ok_measurement_map_missing";
  else
    rs485Reason = MINI_FLOOD_RS485_PROBE_ENABLED ? "probe_no_response" : "probe_disabled";
  json += "\"reason\":\"" + rs485Reason + "\"";
#endif
  json += "},";
  json += "\"queue_count\":" + String(queueCount) + ",";
  json += "\"uptime_ms\":" + String(millis());
  json += "}";
  return json;
}

void printHealth() {
  Serial.printf(
      "[HEALTH] profile=%s wifi=%s backend=%s(http=%d) water=%s rain=%s rs485=%s\n",
      HARDWARE_PROFILE,
      WiFi.status() == WL_CONNECTED ? "OK" : "FAIL",
      backendConnected ? "OK" : "FAIL", lastHttpStatus,
      waterSensorConnected ? "OK" : "FAIL", rainSensorMode.c_str(),
#if defined(MINI_FLOOD_PROFILE_REAL_HARDWARE)
      rs485Connected ? (rainSensorVerified ? "DATA_OK" : "LINK_OK") : "FAIL");
#else
      "SIMULATION");
#endif
}

void updateStatusLeds() {
  bool wifiConnected = WiFi.status() == WL_CONNECTED;
  digitalWrite(PIN_LED_WIFI, wifiConnected ? HIGH : LOW);
  digitalWrite(PIN_LED_BACKEND, backendConnected ? HIGH : LOW);
  digitalWrite(PIN_LED_WATER, waterSensorConnected ? HIGH : LOW);
#if defined(MINI_FLOOD_PROFILE_REAL_HARDWARE)
  // Tren phan cung that, LED trang xac nhan duong RS485 co frame CRC hop le.
  // Viec register co dung la luong mua hay khong duoc bao rieng boi
  // rainSensorVerified va trang /health.
  digitalWrite(PIN_LED_RAIN, rs485Connected ? HIGH : LOW);
#else
  digitalWrite(PIN_LED_RAIN, rainSensorVerified ? HIGH : LOW);
#endif

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

#if defined(MINI_FLOOD_PROFILE_SIMULATION)
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
#else
uint16_t modbusCrc16(const uint8_t *data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t index = 0; index < length; index++) {
    crc ^= data[index];
    for (uint8_t bit = 0; bit < 8; bit++) {
      bool lsb = crc & 0x0001;
      crc >>= 1;
      if (lsb)
        crc ^= 0xA001;
    }
  }
  return crc;
}

float readRealWaterDistance(bool &valid) {
  const int attempts = 3;
  float distanceTotal = 0.0f;
  int validCount = 0;
  for (int attempt = 0; attempt < attempts; attempt++) {
    digitalWrite(PIN_TRIG_WATER, LOW);
    delayMicroseconds(3);
    digitalWrite(PIN_TRIG_WATER, HIGH);
    delayMicroseconds(10);
    digitalWrite(PIN_TRIG_WATER, LOW);

    unsigned long duration = pulseIn(PIN_ECHO_WATER, HIGH, 30000);
    float distance = duration * 0.0343f / 2.0f;
    if (duration > 0 && distance >= 2.0f && distance <= 400.0f) {
      distanceTotal += distance;
      validCount++;
    }
    delay(60);
  }
  valid = validCount >= 2;
  lastWaterDistanceCM = valid ? distanceTotal / validCount : -1.0f;
  lastWaterLevelCM = valid ? max(0.0f, SENSOR_MOUNT_HEIGHT_CM - lastWaterDistanceCM)
                            : 0.0f;
  return lastWaterLevelCM;
}

bool discoverRainSensorAtBaud(uint32_t baud, uint8_t &discoveredAddress) {
  Serial2.end();
  delay(30);
  Serial2.begin(baud, MINI_FLOOD_RAIN_MODBUS_SERIAL_CONFIG, PIN_RS485_RX,
                PIN_RS485_TX);
  delay(80);
  while (Serial2.available())
    Serial2.read();

  // Lenh lookup dia chi theo tai lieu SN/SW-3001-GYL-N01.
  // FF 03 07 D0 00 01 91 59: chi doc register dia chi, khong ghi cau hinh.
  uint8_t request[8] = {0xFF, 0x03, 0x07, 0xD0, 0x00, 0x01, 0x00, 0x00};
  uint16_t requestCrc = modbusCrc16(request, 6);
  request[6] = requestCrc & 0xFF;
  request[7] = requestCrc >> 8;

  Serial.printf("[RS485-DISCOVERY] baud=%lu TX:",
                static_cast<unsigned long>(baud));
  for (uint8_t value : request)
    Serial.printf(" %02X", value);
  Serial.println();
  Serial2.write(request, sizeof(request));
  Serial2.flush();

  uint8_t response[16] = {0};
  size_t received = 0;
  unsigned long started = millis();
  unsigned long lastByteAt = started;
  while (received < sizeof(response) && millis() - started < 800) {
    if (Serial2.available()) {
      response[received++] = static_cast<uint8_t>(Serial2.read());
      lastByteAt = millis();
    } else if (received > 0 && millis() - lastByteAt >= 30) {
      break;
    } else {
      delay(2);
    }
  }

  Serial.printf("[RS485-DISCOVERY] baud=%lu RX:",
                static_cast<unsigned long>(baud));
  if (received == 0)
    Serial.print(" <timeout>");
  for (size_t index = 0; index < received; index++)
    Serial.printf(" %02X", response[index]);
  Serial.println();

  if (received != 7)
    return false;
  uint16_t responseCrc = static_cast<uint16_t>(response[5]) |
                         (static_cast<uint16_t>(response[6]) << 8);
  if (modbusCrc16(response, 5) != responseCrc || response[0] != 0xFF ||
      response[1] != 0x03 || response[2] != 0x02 || response[3] != 0x00 ||
      response[4] == 0x00 || response[4] == 0xFF) {
    return false;
  }

  discoveredAddress = response[4];
  lastRs485ResponseBytes = received;
  lastRainResponseMs = millis();
  rs485Connected = true;
  return true;
}

bool discoverRainSensorModbus() {
  lastRs485DiscoveryAt = millis();
  const uint32_t baudCandidates[] = {2400, 4800, 9600};
  Serial.println("[RS485-DISCOVERY] Bat dau quet read-only 2400/4800/9600");
  for (uint32_t baud : baudCandidates) {
    uint8_t discoveredAddress = 0;
    if (discoverRainSensorAtBaud(baud, discoveredAddress)) {
      activeRainBaud = baud;
      activeRainSlaveId = discoveredAddress;
      rainModbusDiscovered = true;
      rainSensorMode = "modbus_discovery_ok";
      Serial.printf("[RS485-DISCOVERY] FOUND baud=%lu slave=%u\n",
                    static_cast<unsigned long>(activeRainBaud),
                    activeRainSlaveId);
      return true;
    }
  }

  activeRainBaud = MINI_FLOOD_RAIN_MODBUS_BAUD;
  activeRainSlaveId = MINI_FLOOD_RAIN_MODBUS_SLAVE_ID;
  rainModbusDiscovered = false;
  rs485Connected = false;
  Serial2.end();
  delay(30);
  Serial2.begin(activeRainBaud, MINI_FLOOD_RAIN_MODBUS_SERIAL_CONFIG,
                PIN_RS485_RX, PIN_RS485_TX);
  Serial.println("[RS485-DISCOVERY] Khong tim thay cam bien; khoi phuc cau hinh mac dinh");
  return false;
}

bool readModbusRegister(uint8_t functionCode, uint16_t registerAddress,
                        uint16_t &registerValue, bool &hasRegisterValue) {
  hasRegisterValue = false;
  lastRs485Exception = 0;
  lastRs485ResponseBytes = 0;
  if (functionCode != 0x03 && functionCode != 0x04) {
    rainSensorMode = "unsupported_function";
    return false;
  }

  while (Serial2.available())
    Serial2.read();

  uint8_t request[8] = {
      activeRainSlaveId,
      functionCode,
      static_cast<uint8_t>(registerAddress >> 8),
      static_cast<uint8_t>(registerAddress & 0xFF),
      0x00,
      0x01,
      0x00,
      0x00,
  };
  uint16_t requestCrc = modbusCrc16(request, 6);
  request[6] = requestCrc & 0xFF;
  request[7] = requestCrc >> 8;

  Serial.print("[RS485] TX:");
  for (uint8_t value : request)
    Serial.printf(" %02X", value);
  Serial.println();
  Serial2.write(request, sizeof(request));
  Serial2.flush();

  uint8_t response[32] = {0};
  size_t received = 0;
  unsigned long started = millis();
  unsigned long lastByteAt = started;
  while (received < sizeof(response) && millis() - started < 800) {
    if (Serial2.available()) {
      response[received++] = static_cast<uint8_t>(Serial2.read());
      lastByteAt = millis();
    } else if (received > 0 && millis() - lastByteAt >= 30) {
      break;
    } else {
      delay(2);
    }
  }
  lastRs485ResponseBytes = received;
  Serial.print("[RS485] RX:");
  if (received == 0)
    Serial.print(" <timeout>");
  for (size_t index = 0; index < received; index++)
    Serial.printf(" %02X", response[index]);
  Serial.println();

  if (received < 5) {
    rs485Connected = false;
    rainSensorMode = "modbus_timeout";
    return false;
  }
  uint16_t responseCrc = static_cast<uint16_t>(response[received - 2]) |
                         (static_cast<uint16_t>(response[received - 1]) << 8);
  if (modbusCrc16(response, received - 2) != responseCrc) {
    rs485Connected = false;
    rainSensorMode = "modbus_crc_error";
    return false;
  }
  if (response[0] != activeRainSlaveId) {
    rs485Connected = false;
    rainSensorMode = "modbus_frame_invalid";
    return false;
  }

  if (response[1] == static_cast<uint8_t>(functionCode | 0x80)) {
    if (received != 5) {
      rs485Connected = false;
      rainSensorMode = "modbus_frame_invalid";
      return false;
    }
    rs485Connected = true;
    lastRainResponseMs = millis();
    lastRs485Exception = response[2];
    rainSensorMode = "modbus_exception_0x";
    if (lastRs485Exception < 0x10)
      rainSensorMode += "0";
    rainSensorMode += String(lastRs485Exception, HEX);
    Serial.printf("[RS485] Cam bien co phan hoi, Modbus exception=0x%02X\n",
                  lastRs485Exception);
    return true;
  }
  if (received != 7 || response[1] != functionCode || response[2] != 0x02) {
    rs485Connected = false;
    rainSensorMode = "modbus_frame_invalid";
    return false;
  }

  rs485Connected = true;
  lastRainResponseMs = millis();
  registerValue = (static_cast<uint16_t>(response[3]) << 8) | response[4];
  hasRegisterValue = true;
  return true;
}

float readWaterLevelCM(bool &valid) {
  const int sampleCount = 15;
  int samples[sampleCount];
  for (int index = 0; index < sampleCount; index++) {
    samples[index] = analogRead(PIN_WATER_ANALOG);
    delay(4);
  }
  for (int left = 1; left < sampleCount; left++) {
    int value = samples[left];
    int right = left - 1;
    while (right >= 0 && samples[right] > value) {
      samples[right + 1] = samples[right];
      right--;
    }
    samples[right + 1] = value;
  }

  // Trung binh 9 mau giua de loai xung nhieu cao/thap.
  long total = 0;
  for (int index = 3; index < 12; index++)
    total += samples[index];
  lastWaterAdcRaw = static_cast<int>(total / 9);

  if (!MINI_FLOOD_WATER_CALIBRATED ||
      MINI_FLOOD_WATER_ADC_DRY == MINI_FLOOD_WATER_ADC_FULL) {
    valid = false;
    lastWaterLevelCM = 0.0f;
    return lastWaterLevelCM;
  }

  float normalized =
      static_cast<float>(lastWaterAdcRaw - MINI_FLOOD_WATER_ADC_DRY) /
      static_cast<float>(MINI_FLOOD_WATER_ADC_FULL - MINI_FLOOD_WATER_ADC_DRY);
  if (MINI_FLOOD_WATER_ADC_INVERTED)
    normalized = 1.0f - normalized;
  bool withinElectricalRange = normalized >= -0.15f && normalized <= 1.15f;
  normalized = constrain(normalized, 0.0f, 1.0f);
  lastWaterLevelCM = normalized * MINI_FLOOD_WATER_SENSOR_RANGE_CM;
  valid = withinElectricalRange;
  return lastWaterLevelCM;
}

float readRainRateMMH(bool &rainSensorValid, float intervalHours) {
  if (MINI_FLOOD_RS485_AUTO_DISCOVERY_ENABLED && !rs485Connected &&
      (lastRs485DiscoveryAt == 0 ||
       millis() - lastRs485DiscoveryAt >= MINI_FLOOD_RS485_DISCOVERY_RETRY_MS)) {
    discoverRainSensorModbus();
  }

  uint16_t rawValue = 0;
  bool hasRegisterValue = false;
  uint8_t functionCode = MINI_FLOOD_RAIN_MODBUS_CONFIGURED
                             ? MINI_FLOOD_RAIN_MODBUS_FUNCTION
                             : MINI_FLOOD_RS485_PROBE_FUNCTION;
  uint16_t registerAddress = MINI_FLOOD_RAIN_MODBUS_CONFIGURED
                                 ? MINI_FLOOD_RAIN_MODBUS_REGISTER
                                 : MINI_FLOOD_RS485_PROBE_REGISTER;

  if (!MINI_FLOOD_RAIN_MODBUS_CONFIGURED && !MINI_FLOOD_RS485_PROBE_ENABLED) {
    rainSensorValid = false;
    rainSensorVerified = false;
    rainSensorMode = "modbus_probe_disabled";
    return 0.0f;
  }
  if (!readModbusRegister(functionCode, registerAddress, rawValue,
                          hasRegisterValue)) {
    rainSensorValid = false;
    rainSensorVerified = false;
    return 0.0f;
  }
  if (!MINI_FLOOD_RAIN_MODBUS_CONFIGURED) {
    rainSensorValid = false;
    rainSensorVerified = false;
    if (hasRegisterValue)
      rainSensorMode = "rs485_probe_ok_map_missing";
    return 0.0f;
  }
  if (!hasRegisterValue) {
    rainSensorValid = false;
    rainSensorVerified = false;
    return 0.0f;
  }

  float value = rawValue * MINI_FLOOD_RAIN_MODBUS_SCALE;
  float rateMMH = value;
  if (MINI_FLOOD_RAIN_VALUE_MODE == 1) {
    if (!lastRainTotalValid || intervalHours <= 0.0f) {
      lastRainTotalMM = value;
      lastRainTotalValid = true;
      rateMMH = 0.0f;
    } else {
      float delta = value >= lastRainTotalMM ? value - lastRainTotalMM : value;
      lastRainTotalMM = value;
      rateMMH = delta / intervalHours;
    }
  }

  if (!isfinite(rateMMH) || rateMMH < 0.0f ||
      rateMMH > MINI_FLOOD_RAIN_MAX_RATE_MMH) {
    rainSensorValid = false;
    rainSensorVerified = false;
    rainSensorMode = "modbus_value_out_of_range";
    return 0.0f;
  }
  rainSensorValid = true;
  rainSensorVerified = true;
  rainSensorMode = "modbus_crc_ok";
  return rateMMH;
}
#endif

String buildQualityFlags(bool waterValid) {
  String flags = "[";
  bool hasFlag = false;
  if (!waterValid) {
#if defined(MINI_FLOOD_PROFILE_REAL_HARDWARE)
#if MINI_FLOOD_WATER_SENSOR_HCSR04
    flags += "\"water_sensor_invalid\"";
#else
    flags += MINI_FLOOD_WATER_CALIBRATED ? "\"water_sensor_invalid\"" :
                                           "\"water_not_calibrated\"";
#endif
#else
    flags += "\"water_sensor_timeout\"";
#endif
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

#if defined(MINI_FLOOD_PROFILE_REAL_HARDWARE)
  if (activeApiUrl.length() == 0 && !discoverBackend()) {
    setBackendLed(false);
    Serial.println("[HTTP] Chua tim thay backend qua mDNS");
    return false;
  }
  String targetUrl = activeApiUrl;
#else
  String targetUrl = API_URL;
#endif
  String payload = toJson(record);
  HTTPClient http;
  http.setTimeout(5000);
  if (!http.begin(targetUrl)) {
    setBackendLed(false);
    Serial.printf("[HTTP] Khong the khoi tao URL: %s\n", targetUrl.c_str());
    return false;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);
  Serial.printf("[HTTP] POST seq=%lu -> %s\n", record.sequenceNo,
                targetUrl.c_str());
  Serial.printf("[HTTP] Payload: %s\n", payload.c_str());
  int status = http.POST(payload);
  String response = http.getString();
  http.end();
  if (status < 0) {
    Serial.printf("[HTTP] Loi ket noi %d: %s\n", status,
                  HTTPClient::errorToString(status).c_str());
#if defined(MINI_FLOOD_PROFILE_REAL_HARDWARE)
    // IP laptop co the da doi. Xoa URL dang dung de lan gui sau tu tim lai.
    activeApiUrl = "";
    lastBackendDiscoveryAt = 0;
#endif
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
#if defined(MINI_FLOOD_PROFILE_REAL_HARDWARE)
    discoverBackend(true);
#endif
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
  Serial.printf("[BOOT] Hardware profile: %s\n", HARDWARE_PROFILE);
  char bootIdBuffer[18];
  snprintf(bootIdBuffer, sizeof(bootIdBuffer), "%08lx-%08lx",
           (unsigned long)esp_random(), (unsigned long)esp_random());
  bootId = String(bootIdBuffer);
  Serial.printf("[BOOT] Session: %s\n", bootId.c_str());
#if defined(MINI_FLOOD_PROFILE_REAL_HARDWARE)
  Serial.printf("[BOOT] Backend discovery: %s.local:%u\n", BACKEND_MDNS_HOST,
                BACKEND_MDNS_PORT);
#else
  Serial.printf("[BOOT] API: %s\n", API_URL);
#endif
#if defined(MINI_FLOOD_PROFILE_SIMULATION)
  pinMode(PIN_TRIG_WATER, OUTPUT);
  pinMode(PIN_ECHO_WATER, INPUT);
  pinMode(PIN_TRIG_RAIN, OUTPUT);
  pinMode(PIN_ECHO_RAIN, INPUT);
  pinMode(PIN_RAIN_POT, INPUT);
#else
#if MINI_FLOOD_WATER_SENSOR_HCSR04
  pinMode(PIN_TRIG_WATER, OUTPUT);
  pinMode(PIN_ECHO_WATER, INPUT);
  digitalWrite(PIN_TRIG_WATER, LOW);
#else
  analogReadResolution(12);
  pinMode(PIN_WATER_ANALOG, INPUT);
#endif
  Serial2.begin(MINI_FLOOD_RAIN_MODBUS_BAUD,
                MINI_FLOOD_RAIN_MODBUS_SERIAL_CONFIG, PIN_RS485_RX,
                PIN_RS485_TX);
#if MINI_FLOOD_WATER_SENSOR_HCSR04
  Serial.printf("[BOOT] Water HC-SR04 TRIG=%d ECHO=%d mount=%.1fcm\n",
                PIN_TRIG_WATER, PIN_ECHO_WATER, SENSOR_MOUNT_HEIGHT_CM);
#else
  Serial.printf("[BOOT] Water ADC GPIO=%d calibrated=%s\n", PIN_WATER_ANALOG,
                MINI_FLOOD_WATER_CALIBRATED ? "yes" : "no");
#endif
  Serial.printf("[BOOT] RS485 UART2 RX=%d TX=%d configured=%s\n", PIN_RS485_RX,
                PIN_RS485_TX,
                MINI_FLOOD_RAIN_MODBUS_CONFIGURED ? "yes" : "no");
  Serial.printf("[BOOT] RS485 default baud=%lu slave=%u auto_discovery=%s\n",
                static_cast<unsigned long>(activeRainBaud), activeRainSlaveId,
                MINI_FLOOD_RS485_AUTO_DISCOVERY_ENABLED ? "yes" : "no");
#endif
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

    bool waterValid = false;
#if defined(MINI_FLOOD_PROFILE_SIMULATION)
    // Profile Wokwi: cam bien sieu am 1 do muc nuoc.
    float waterDistCM = readEchoDistance(PIN_TRIG_WATER, PIN_ECHO_WATER,
                                         waterValid, SENSOR_MOUNT_HEIGHT_CM);
    float waterLevelCM = max(0.0f, SENSOR_MOUNT_HEIGHT_CM - waterDistCM);
#else
    // Profile that: HC-SR04 do khoang cach tu dau do den mat nuoc.
#if MINI_FLOOD_WATER_SENSOR_HCSR04
    float waterLevelCM = readRealWaterDistance(waterValid);
#else
    float waterLevelCM = readWaterLevelCM(waterValid);
#endif
#endif
    waterSensorConnected = waterValid;

    float intervalHours = elapsedMs / 3600000.0f;
    bool rainValid = false;
#if defined(MINI_FLOOD_PROFILE_SIMULATION)
    // Profile Wokwi: HC-SR04 thu hai hoac bien tro.
    float rainRateMMH = readRainRateMMH(rainValid);
#else
    // Profile that: truy van cam bien mua Modbus qua UART2.
    float rainRateMMH = readRainRateMMH(rainValid, intervalHours);
#endif

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
    Serial.printf(
        "[SENSOR] profile=%s seq=%lu water=%.2fcm rain=%.2fmm/h queue=%d",
        HARDWARE_PROFILE, sequenceNo, waterLevelCM, rainRateMMH, queueCount);
#if defined(MINI_FLOOD_PROFILE_REAL_HARDWARE)
#if MINI_FLOOD_WATER_SENSOR_HCSR04
    Serial.printf(" distance=%.2fcm rain_mode=%s", lastWaterDistanceCM,
                  rainSensorMode.c_str());
#else
    Serial.printf(" adc=%d rain_mode=%s", lastWaterAdcRaw,
                  rainSensorMode.c_str());
#endif
#endif
    Serial.println();
    printHealth();
  }

  ensureWiFi();
  flushQueue();
  healthServer.handleClient();
  updateStatusLeds();
  delay(250);
}
