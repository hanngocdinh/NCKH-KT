/*
  sketch_arduino_uno.ino — Trạm IoT Cảnh báo Lũ lụt (Arduino Uno)
  Môi trường: Wokwi Arduino Uno (https://wokwi.com/projects/new/arduino-uno)
  Kết nối: AI Core Engine qua Serial (JSON stream)
*/

#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// Màn hình LCD 1602 I2C (địa chỉ 0x27)
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Định nghĩa chân cắm trên Arduino Uno
const int PIN_TRIG = 9;         // Chân phát siêu âm HC-SR04
const int PIN_ECHO = 10;        // Chân thu siêu âm HC-SR04
const int PIN_RAIN_POT = A0;    // Chiết áp mô phỏng cảm biến lượng mưa
const int PIN_LED_GREEN = 4;    // Đèn Xanh: An toàn
const int PIN_LED_YELLOW = 3;   // Đèn Vàng: Cảnh báo
const int PIN_LED_RED = 2;      // Đèn Đỏ: Nguy hiểm cao
const int PIN_BUZZER = 5;       // Còi báo động

// Tham số đo đạc vật lý
const float SENSOR_HEIGHT_CM = 400.0; // Chiều cao gắn cảm biến tới đáy rãnh (cm)
float last_water_level_cm = 50.0;

void setup() {
  Serial.begin(9600); // Tốc độ chuẩn cho Arduino Uno

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
  lcd.print("AI IOT FLOOD SYS");
  lcd.setCursor(0, 1);
  lcd.print("THPT TRANQUYCAP ");
  delay(1200);
  lcd.clear();
}

// Đo khoảng cách bằng sóng siêu âm
float readDistanceCM() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  long duration = pulseIn(PIN_ECHO, HIGH, 25000);
  if (duration == 0) return SENSOR_HEIGHT_CM;
  return duration * 0.034 / 2.0;
}

void loop() {
  // 1. Đọc cảm biến siêu âm -> Mực nước thực tế
  float dist_cm = readDistanceCM();
  float water_level_cm = SENSOR_HEIGHT_CM - dist_cm;
  if (water_level_cm < 0) water_level_cm = 0;

  // 2. Tính độ dâng nước delta
  float delta_wl = water_level_cm - last_water_level_cm;
  last_water_level_cm = water_level_cm;

  // 3. Đọc lượng mưa giả lập từ chiết áp A0 (0 -> 150 mm)
  int pot_val = analogRead(PIN_RAIN_POT);
  float rain_daily_mm = map(pot_val, 0, 1023, 0, 150);

  // 4. Kiểm tra phản hồi quyết định từ AI qua Serial (nếu Python gửi về)
  // Format: "RISK:0", "RISK:1", hoặc "RISK:2"
  int risk_level = 0;
  if (Serial.available() > 0) {
    String msg = Serial.readStringUntil('\n');
    msg.trim();
    if (msg.startsWith("RISK:")) {
      risk_level = msg.substring(5).toInt();
    }
  } else {
    // Logic dự phòng tại biên (Edge fallback) nếu chưa nối máy tính:
    if (water_level_cm >= 300.0 || (water_level_cm >= 200.0 && rain_daily_mm > 50.0)) {
      risk_level = 2; // Nguy hiểm cao
    } else if (water_level_cm >= 200.0 || rain_daily_mm > 30.0) {
      risk_level = 1; // Cảnh báo
    } else {
      risk_level = 0; // An toàn
    }
  }

  // 5. Điều khiển thiết bị ngoại vi
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
  } else {
    digitalWrite(PIN_LED_GREEN, LOW);
    digitalWrite(PIN_LED_YELLOW, LOW);
    digitalWrite(PIN_LED_RED, HIGH);
    tone(PIN_BUZZER, 1200, 250); // Còi hú ngắt quãng
  }

  // 6. Cập nhật LCD
  lcd.setCursor(0, 0);
  lcd.print("W:" + String((int)water_level_cm) + "cm R:" + String((int)rain_daily_mm) + "mm  ");
  lcd.setCursor(0, 1);
  if (risk_level == 0) lcd.print("[AI: AN TOAN]   ");
  else if (risk_level == 1) lcd.print("[AI: CANH BAO]  ");
  else lcd.print("[AI: NGUY HIEM] ");

  // 7. Xuất chuỗi JSON chuẩn lên cổng Serial cho AI Backend tiếp nhận
  Serial.print("{\"water_level_cm\":");
  Serial.print(water_level_cm, 1);
  Serial.print(",\"rain_daily_mm\":");
  Serial.print(rain_daily_mm, 1);
  Serial.print(",\"delta_water_level_cm\":");
  Serial.print(delta_wl, 1);
  Serial.println("}");

  delay(2000); // Chu kỳ gửi 2 giây/lần
}
