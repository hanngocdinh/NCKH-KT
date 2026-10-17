# Hướng Dẫn Mô Phỏng Wokwi ESP32 — Mini Flood AI Station

Tài liệu này hướng dẫn cách chạy mô phỏng trạm IoT đo mưa và mực nước cảnh báo ngập cục bộ trên **Wokwi Simulator**, kết nối trực tiếp với backend **FastAPI** và kiểm thử luồng cảnh báo.

---

## 1. Thành phần phần cứng trong mô phỏng

File cấu hình: [`diagram.json`](./diagram.json)

| Linh kiện | Chân ESP32 | Chức năng trong mô hình |
|---|---|---|
| **ESP32 DevKit v4** | - | Vi điều khiển trung tâm |
| **HC-SR04 Ultrasonic** | TRIG: `GPIO 18`, ECHO: `GPIO 19` | Đo khoảng cách từ nóc hố đến mặt nước (hố sâu 40 cm) |
| **Potentiometer (Biến trở)** | SIG: `GPIO 34` (ADC) | Giả lập cảm biến đo cường độ mưa (0 – 120 mm/h) |
| **LCD 1602 (I2C)** | SDA: `GPIO 21`, SCL: `GPIO 22` | Hiển thị mực nước, cường độ mưa và mức cảnh báo |
| **LED Xanh (Green)** | `GPIO 25` | Mức 0 — An toàn |
| **LED Vàng (Yellow)** | `GPIO 26` | Mức 1 — Có nguy cơ |
| **LED Đỏ (Red)** | `GPIO 27` | Mức 2 — Nguy hiểm cao |
| **Buzzer (Còi chíp)** | `GPIO 32` | Còi báo động khi rủi ro Mức 2 |

---

## 2. Cách khởi chạy trên Wokwi

1. Truy cập [Wokwi ESP32 Simulator](https://wokwi.com/projects/new/esp32).
2. Chuyển sang chế độ xem file:
   - Dán nội dung [`diagram.json`](./diagram.json) vào tab `diagram.json`.
   - Dán nội dung [`sketch.ino`](./sketch.ino) vào tab `sketch.ino`.
   - Thêm tab `libraries.txt` và khai báo:
     ```text
     ArduinoJson
     LiquidCrystal I2C
     ```
3. Nhấn nút **Play (Start Simulation)** để bắt đầu chạy.

---

## 3. Kết nối với FastAPI Backend trên Laptop

Khi chạy Wokwi trên trình duyệt và backend FastAPI chạy trên máy tính:
1. Chạy backend cục bộ:
   ```bash
   uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
   ```
2. Cài đặt **Wokwi IoT Gateway** (hoặc dùng đường hầm như ngrok/cloudflared nếu muốn URL công khai):
   - Thay `API_URL` trong `sketch.ino`:
     ```cpp
     const char* API_URL = "http://<IP_MAY_TINH>:8000/api/v1/telemetry";
     const char* DEVICE_KEY = "change-me"; // Phải khớp với MINI_FLOOD_DEVICE_KEY trong .env
     ```

---

## 4. Các kịch bản thử nghiệm trực tiếp trên Wokwi

### Kịch bản 1: Mức An toàn (Mức 0)
- Kéo khoảng cách cảm biến siêu âm HC-SR04: `30 cm` (mực nước hố ga = 40 - 30 = `10 cm` < 15 cm).
- Xoay biến trở mưa về mức thấp: `< 15 mm/h`.
- **Kết quả quan sát**: LED Xanh sáng, LED Vàng và Đỏ tắt, Còi im lặng, LCD hiển thị `[0: AN TOAN]`.

### Kịch bản 2: Có nguy cơ (Mức 1)
- Kéo khoảng cách HC-SR04: `20 cm` (mực nước = `20 cm`, nằm trong khoảng 15 - 25 cm) **HOẶC** xoay biến trở mưa lên `35 mm/h`.
- **Kết quả quan sát**: LED Xanh tắt, LED Vàng sáng, LED Đỏ tắt, Còi im lặng, LCD hiển thị `[1: NGUY CO]`.

### Kịch bản 3: Nguy hiểm cao (Mức 2)
- Kéo khoảng cách HC-SR04: `10 cm` (mực nước = `30 cm` >= 25 cm) **HOẶC** tăng mưa lên `50 mm/h` kèm nước dâng nhanh.
- **Kết quả quan sát**: LED Đỏ sáng, Còi hú ngắt quãng theo nhịp, LCD hiển thị `[2: NGUY HIEM!]`.

### Kịch bản 4: Kiểm tra Fallback khi Mất Mạng (Offline Mode)
- Đổi SSID thành một tên không tồn tại để ngắt kết nối WiFi.
- **Kết quả quan sát**:
  - Thiết bị tự động chuyển sang Cây quyết định an toàn tại chỗ (`OFFLINE_FALLBACK`).
  - Dữ liệu đo đạc được lưu đệm vào hàng đợi `pending[]`.
  - Đèn và còi vẫn phản ứng chuẩn xác theo ngưỡng nước và mưa hiện tại.
  - Khi khôi phục kết nối, hàm `flushQueue()` tự động đẩy dữ liệu đệm lên server.
