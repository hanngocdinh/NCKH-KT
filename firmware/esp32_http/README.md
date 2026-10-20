# ESP32 HTTP telemetry

Firmware `mini_flood_station.ino` thực hiện ba nhiệm vụ:

1. Đọc cảm biến mưa và mực nước.
2. Gửi telemetry đến `POST /api/v1/telemetry` mỗi phút.
3. Lưu đệm tối đa 100 bản ghi trong RAM khi mất Wi-Fi và gửi lại sau.

ESP32 không nhận mức cảnh báo, không điều khiển LED và không điều khiển còi từ phản hồi của backend. HTTP response chỉ được dùng để xác nhận server đã nhận bản ghi.

Wokwi có thể dùng biến trở để mô phỏng cường độ mưa. Khi dùng cảm biến mưa RS485 thật, thay `readRainRateMMH()` bằng hàm đọc Modbus theo datasheet thiết bị.

## Mô phỏng bằng Wokwi Extension trên VS Code

1. File sơ đồ mạch: [diagram.json](file:///d:/Projects/tool-craw/firmware/esp32_http/diagram.json) (đã khai báo ESP32, HC-SR04 ở chân 18-19, biến trở mưa ở chân 34).
2. Khi chạy trong Wokwi VS Code Extension, ESP32 kết nối về backend trên laptop qua địa chỉ:
   ```cpp
   const char* API_URL = "http://host.wokwi.internal:8000/api/v1/telemetry";
   ```
   (`host.wokwi.internal` là hostname ảo do Wokwi tự động ánh xạ về localhost của máy tính).
