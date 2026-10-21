# ESP32 HTTP telemetry

Firmware `src/main.cpp` thực hiện bốn nhiệm vụ:

1. Đọc cảm biến mưa và mực nước.
2. Gửi telemetry đến `POST /api/v2/telemetry` mỗi 5 giây trong chế độ test; khi vận hành thật nên đổi thành 60 giây.
3. Lưu đệm tối đa 100 bản ghi trong RAM khi mất Wi-Fi và gửi lại sau.
4. Tự chẩn đoán Wi-Fi, backend và từng đầu vào cảm biến qua trang `/health`.

## Cấu hình riêng cho thiết bị thật

Sao chép `include/secrets.h.example` thành `include/secrets.h`, sau đó điền Wi-Fi, URL backend và device key. File `secrets.h` đã bị Git bỏ qua để không đưa mật khẩu lên repository.

Không cố định COM trong `platformio.ini` vì số cổng có thể đổi khi cắm lại USB. Khi cần có thể nạp bằng `pio run -t upload --upload-port COM6` và mở monitor bằng `pio device monitor --port COM6`.

## Sơ đồ LED chẩn đoán

Mỗi LED ngoài phải mắc `GPIO -> điện trở 220-330 ohm -> chân dương LED`, chân âm LED về `GND`:

| LED đề nghị | GPIO | Sáng khi |
|---|---:|---|
| Xanh dương — Wi-Fi | 25 | ESP32 đã vào Wi-Fi |
| Xanh lá — Backend | 26 | Lần gửi gần nhất nhận HTTP 2xx |
| Vàng — Mực nước | 27 | HC-SR04 mực nước đạt ít nhất 2/3 Echo hợp lệ |
| Trắng — Mưa | 33 | HC-SR04 mưa đạt ít nhất 2/3 Echo hợp lệ |

LED D2 trên bo là trạng thái tổng hợp:

- Sáng liên tục: cả bốn cụm đều OK.
- Một chớp chậm: Wi-Fi hoặc backend lỗi.
- Hai chớp nhanh: mạng OK nhưng có ít nhất một cảm biến lỗi.

Đây là LED chẩn đoán kết nối, không biểu thị mức An toàn/Cảnh báo/Nguy hiểm.

Mỗi HC-SR04 được TRIG ba lần và chỉ được coi là kết nối khi ít nhất hai Echo nằm trong khoảng 2-400 cm. Hai lần TRIG cách nhau 60 ms để hạn chế nhiễu chéo giữa cảm biến.

## Kiểm tra từng cụm trên thiết bị thật

Sau khi Serial Monitor in địa chỉ IP, mở `http://<IP-ESP32>/health`. Kết quả JSON cho biết:

- `wifi.connected`: ESP32 đã vào Wi-Fi hay chưa.
- `backend.connected`: lần gửi HTTP gần nhất có được backend chấp nhận hay không.
- `water_sensor.connected`: HC-SR04 mực nước có trả xung Echo hay không.
- `rain_sensor.verified`: đầu vào mưa có được xác minh hay chỉ đang dùng analog dự phòng.
- `rs485`: hiện báo `missing_modbus_register_map`; chưa được phép coi là kết nối cho đến khi khai báo đúng model cảm biến, slave ID, baud/parity và thanh ghi Modbus.

Serial cũng in một dòng tổng hợp sau mỗi lần đo, ví dụ:

```text
[HEALTH] wifi=OK backend=OK(http=200) water=FAIL rain=analog_fallback_unverified rs485=NOT_CONFIGURED
```

Không dùng `ping` mạng để kiểm tra mọi thiết bị: HC-SR04 được kiểm tra bằng xung Echo, RS485 bằng request/response Modbus hợp lệ, Wi-Fi bằng trạng thái kết nối và backend bằng HTTP 2xx.

Wokwi có thể dùng biến trở để mô phỏng cường độ mưa. Khi dùng cảm biến mưa RS485 thật, thay `readRainRateMMH()` bằng hàm đọc Modbus theo datasheet thiết bị.

`SENSOR_MOUNT_HEIGHT_CM` là khoảng cách từ đầu dò đến đáy dùng để tính `water_level_cm`. Ngưỡng nước tràn là `overflow_level_cm` trong cấu hình backend/dashboard; hai giá trị này không nên bị hiểu là một.

## Mô phỏng bằng Wokwi Extension trên VS Code

1. Luôn mở Wokwi từ thư mục gốc của dự án; đây là nơi duy nhất chứa `wokwi.toml` và `diagram.json`.
2. Build bằng `pio run --project-dir EPS32_PROJECT`. Wokwi nạp artifact V2 trong `EPS32_PROJECT/.pio/build/esp32dev`.
3. File sơ đồ mạch chuẩn: [diagram.json](file:///d:/Projects/tool-craw/diagram.json) (đã khai báo ESP32, HC-SR04 ở chân 18-19, biến trở mưa ở chân 34).
4. Khi chạy trong Wokwi VS Code Extension, ESP32 kết nối về backend trên laptop qua địa chỉ:
   ```cpp
   const char* API_URL = "http://host.wokwi.internal:8000/api/v2/telemetry";
   ```
   (`host.wokwi.internal` là hostname ảo do Wokwi tự động ánh xạ về localhost của máy tính).

Serial Monitor phải hiện `[BOOT] Mini Flood firmware V2`, sau đó là trạng thái Wi-Fi và dòng `POST`/`Phan hoi`. Nếu chạy Wokwi trên trình duyệt thay vì Extension, `host.wokwi.internal` không trỏ về backend cục bộ; cần dùng một URL HTTPS public/tunnel cho `API_URL`.
