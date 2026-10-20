# ESP32 HTTP telemetry

Firmware `src/main.cpp` thực hiện ba nhiệm vụ:

1. Đọc cảm biến mưa và mực nước.
2. Gửi telemetry đến `POST /api/v2/telemetry` mỗi phút.
3. Lưu đệm tối đa 100 bản ghi trong RAM khi mất Wi-Fi và gửi lại sau.

ESP32 không nhận mức cảnh báo, không điều khiển LED và không điều khiển còi từ phản hồi của backend. HTTP response chỉ được dùng để xác nhận server đã nhận bản ghi.

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
