/*
  sketch.ino – Mô phỏng Trạm đo IoT AI Cảnh báo Ngập (THPT Trần Quý Cáp)
  Môi trường: Wokwi ESP32 Simulator
*/

#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// Khởi tạo màn hình LCD 1602 I2C địa chỉ 0x27
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Định nghĩa chân phần cứng kết nối theo diagram.json
#define PIN_TRIG 18
#define PIN_ECHO 19
#define PIN_RAIN_POT 34   // Giả lập đọc tín hiệu RS485 đo mưa
#define PIN_LED_GREEN 25  // Nhãn 0: An toàn
#define PIN_LED_YELLOW 26 // Nhãn 1: Có nguy cơ
#define PIN_LED_RED 27    // Nhãn 2: Nguy cơ cao
#define PIN_BUZZER 32     // Còi báo động

// Cấu hình vật lý của hố ga / rãnh thoát nước thực nghiệm
const float SENSOR_MOUNT_HEIGHT_CM = 400.0; // Cảm biến gắn cách đáy hố 400 cm
float last_water_level_cm = 50.0;

void setup() {
  Serial.begin(115200);
  Serial.println("\n[SYSTEM] Khoi dong He thong IoT AI Canh bao Ngap Hoi An...");

  // Cấu hình chân GPIO
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_RAIN_POT, INPUT);
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_YELLOW, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);

  // Khởi động màn hình LCD
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("AI FLOOD SYSTEM");
  lcd.setCursor(0, 1);
  lcd.print("THPT TRANQUYCAP");
  delay(1500);
  lcd.clear();
}

// Hàm đo khoảng cách bằng sóng siêu âm
float readDistanceCM() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  
  long duration = pulseIn(PIN_ECHO, HIGH, 30000);
  if (duration == 0) return SENSOR_MOUNT_HEIGHT_CM;
  return duration * 0.034 / 2.0;
}

void loop() {
  // 1. Đọc cảm biến khoảng cách và quy đổi ra mực nước hiện tại (X3)
  float dist_cm = readDistanceCM();
  float water_level_cm = SENSOR_MOUNT_HEIGHT_CM - dist_cm;
  if (water_level_cm < 0) water_level_cm = 0;

  // 2. Tính tốc độ biến thiên mực nước Δh (X4)
  float delta_h = water_level_cm - last_water_level_cm;
  last_water_level_cm = water_level_cm;

  // 3. Đọc lượng mưa giả lập từ cảm biến mưa RS485 (X2)
  int pot_val = analogRead(PIN_RAIN_POT);
  float rain_intensity_mmh = map(pot_val, 0, 4095, 0, 120); // 0 - 120 mm/h
  float rain_15m_accum = rain_intensity_mmh * 0.25;          // Tích lũy 15 phút (X1)

  // 4. Thuật toán AI phân loại nguy cơ ngập (Decision Logic)
  // Ngưỡng: BĐ1 = 200 cm, BĐ2 = 300 cm
  int risk_level = 0;
  String risk_desc = "AN TOAN";

  if (water_level_cm >= 300.0 || (water_level_cm >= 220.0 && delta_h > 20.0) || (rain_intensity_mmh > 60.0 && water_level_cm > 200.0)) {
    risk_level = 2; // Nguy cơ cao
    risk_desc = "NGUY CO CAO";
  } else if (water_level_cm >= 200.0 || rain_intensity_mmh > 30.0 || delta_h > 15.0) {
    risk_level = 1; // Có nguy cơ
    risk_desc = "CO NGUY CO";
  } else {
    risk_level = 0; // An toàn
    risk_desc = "AN TOAN";
  }

  // 5. Điều khiển thiết bị cảnh báo phần cứng
  if (risk_level == 0) {
    digitalWrite(PIN_LED_GREEN, HIGH);
    digitalWrite(PIN_LED_YELLOW, LOW);
    digitalWrite(PIN_LED_RED, LOW);
    noTone(PIN_BUZZER);
  } else if (risk_level == 1) {
    digitalWrite(PIN_LED_GREEN, LOW);
    digitalWrite(PIN_LED_YELLOW, HIGH);
    digitalWrite(PIN_LED_RED, LOW);
    noTone(PIN_BUZZER);
  } else { // Risk level 2: Cảnh báo đỏ + Còi hú
    digitalWrite(PIN_LED_GREEN, LOW);
    digitalWrite(PIN_LED_YELLOW, LOW);
    digitalWrite(PIN_LED_RED, HIGH);
    tone(PIN_BUZZER, 1000, 300); // Kêu còi ngắt quãng
  }

  // 6. Cập nhật màn hình LCD hiển thị
  lcd.setCursor(0, 0);
  lcd.print("M:" + String((int)water_level_cm) + "cm R:" + String((int)rain_intensity_mmh) + "mm/h ");
  lcd.setCursor(0, 1);
  lcd.print("[" + risk_desc + "]    ");

  // 7. Xuất gói tin JSON truyền lên Cloud qua Serial
  Serial.print("{\"rain_accum_mm\":");
  Serial.print(rain_15m_accum, 1);
  Serial.print(",\"rain_rate_mmh\":");
  Serial.print(rain_intensity_mmh, 1);
  Serial.print(",\"water_level_cm\":");
  Serial.print(water_level_cm, 1);
  Serial.print(",\"delta_h_cm\":");
  Serial.print(delta_h, 1);
  Serial.print(",\"risk_level\":");
  Serial.print(risk_level);
  Serial.print(",\"status\":\"");
  Serial.print(risk_desc);
  Serial.println("\"}");

  delay(2000); // Chu kỳ cập nhật mô phỏng 2 giây
}
