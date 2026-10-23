# Giải thích thiết bị trong hệ thống IoT giám sát mưa và mực nước

Tài liệu này giải thích công dụng, nguyên lý hoạt động, dữ liệu đầu vào/đầu ra và cách kiểm tra từng thiết bị trong hệ thống.

Sơ đồ đấu dây tham khảo: [Sơ đồ ESP32, HC-SR04 và RS485](../EPS32_PROJECT/docs/images/so-do-dau-day-esp32-hcsr04-rs485.svg).

## 1. Tổng quan luồng hoạt động

```text
Cảm biến mực nước ──Trig/Echo──┐
                               ├──> ESP32 ──Wi-Fi/HTTP──> Backend
Cảm biến mưa ──RS485───────────┘                         │
                                                     ├──> Lưu dữ liệu
                                                     ├──> Dự báo AI
                                                     ├──> Dashboard
                                                     └──> Telegram
```

Hệ thống có ba lớp:

1. **Lớp cảm biến:** biến đại lượng vật lý thành tín hiệu điện hoặc dữ liệu số.
2. **Lớp ESP32:** đọc, kiểm tra, chuẩn hóa và gửi dữ liệu.
3. **Lớp backend:** lưu dữ liệu, dự báo mực nước và xác định trạng thái cảnh báo.

## 2. ESP32 — bộ điều khiển trung tâm

ESP32 là bộ xử lý chính tại trạm. Nó có các nhiệm vụ:

- Phát xung Trig và đo xung Echo của cảm biến mực nước HC-SR04.
- Gửi yêu cầu và nhận phản hồi Modbus từ cảm biến mưa.
- Kiểm tra dữ liệu cảm biến có hợp lệ hay không.
- Chuyển dữ liệu thô thành đơn vị `cm`, `mm` hoặc `mm/h`.
- Kết nối Wi-Fi.
- Gửi telemetry đến backend bằng HTTP.
- Điều khiển các LED chẩn đoán.
- Lưu tạm dữ liệu khi backend hoặc Wi-Fi bị gián đoạn.

### 2.1 Phân công GPIO cho phần cứng thật

| Chân ESP32 | Công dụng |
|---:|---|
| `GPIO18` | Phát xung `TRIG` tới HC-SR04 đo mực nước |
| `GPIO19` | Nhận xung `ECHO` từ HC-SR04 qua cầu chia áp 5 V xuống khoảng 3,3 V |
| `GPIO16 / RX2` | Nhận dữ liệu từ TX của module TTL–RS485 |
| `GPIO17 / TX2` | Gửi dữ liệu vào RX của module TTL–RS485 |
| `GPIO25` | LED trạng thái Wi-Fi |
| `GPIO26` | LED trạng thái backend |
| `GPIO27` | LED trạng thái cảm biến mực nước |
| `GPIO33` | LED trạng thái cảm biến mưa |
| `GPIO2 / D2` | LED trạng thái tổng hợp |

UART0 qua cổng USB được dành cho nạp firmware và Serial Monitor. UART2 tại GPIO16/17 được dành cho cảm biến mưa RS485.

### 2.2 Dữ liệu ESP32 nhận được

- Từ cảm biến nước: độ rộng xung Echo tính bằng microsecond; firmware đổi thành khoảng cách từ đầu dò tới mặt nước rồi tính `water_level_cm`.
- Từ cảm biến mưa: một khung byte Modbus RTU có địa chỉ thiết bị, mã hàm, dữ liệu và CRC.

### 2.3 Cách kiểm tra ESP32

1. Cắm cáp USB có truyền dữ liệu.
2. Kiểm tra cổng COM xuất hiện trong Device Manager.
3. Mở Serial Monitor ở `115200` baud.
4. Nhấn nút EN/RESET.
5. Với firmware thật, log phải có:

```text
[BOOT] Hardware profile: real_hardware
```

Nếu log ghi `simulation`, firmware đang dùng cảm biến Wokwi và dữ liệu không được dùng để huấn luyện model thật.

## 3. Bo mở rộng ESP32

Bo mở rộng màu đen có nhiệm vụ:

- Giữ ESP32 chắc chắn.
- Đưa các chân GPIO ra đầu nối dễ cắm dây.
- Phân phối các đường `3V3`, `5V` và `GND`.
- Cung cấp jack DC.
- Có thể chứa mạch ổn áp cho ESP32.

Bo mở rộng không đo cảm biến, không giao tiếp Modbus và không xử lý AI. Nó chỉ hỗ trợ kết nối và cấp nguồn.

Trước khi dùng adapter 12 V phải đọc điện áp đầu vào được in trên bo hoặc tài liệu của đúng model. Jack cắm vừa không có nghĩa bo chắc chắn chịu được 12 V.

## 4. Adapter nguồn DC

Adapter chuyển điện lưới AC thành điện một chiều DC:

```text
Điện lưới AC → adapter → điện DC → bo mở rộng → ESP32
```

Các thông số phải kiểm tra:

- Điện áp đầu ra.
- Dòng điện tối đa.
- Cực tính đầu jack.
- Điện áp đầu vào cho phép của bo mở rộng.

Không đưa 12 V trực tiếp vào:

- Chân GPIO của ESP32.
- Chân `3V3`.
- Chân `5V` nếu bo không cho phép.
- Chân `VCC` của module TTL–RS485.

### Kiểm tra nguồn

- Đo điện áp adapter bằng đồng hồ trước khi cắm.
- Kiểm tra đúng cực tính.
- LED nguồn phải sáng ổn định.
- ESP32 không nóng bất thường hoặc reset liên tục.

## 5. Cảm biến mực nước HC-SR04

HC-SR04 là cảm biến khoảng cách siêu âm có bốn chân:

| Chân | Kết nối |
|---|---|
| `VCC` | `5V` |
| `GND` | `GND` chung |
| `TRIG` | `GPIO18` |
| `ECHO` | `GPIO19` qua cầu chia áp |

### 5.1 Nguyên lý hoạt động

ESP32 phát một xung ngắn vào `TRIG`. HC-SR04 phát sóng siêu âm, nhận tiếng dội từ mặt nước và trả một xung tại `ECHO`; độ rộng xung biểu diễn thời gian sóng đi và về.

```text
Độ rộng xung Echo
→ khoảng cách đầu dò tới mặt nước
→ water_level_cm = chiều cao lắp cảm biến - khoảng cách
```

`SENSOR_MOUNT_HEIGHT_CM` là khoảng cách từ mặt đầu dò tới đáy bể khi bể rỗng. Đây là giá trị lắp đặt, không phải ngưỡng tràn của backend. Firmware lấy ba lần đo và chỉ công nhận cảm biến hoạt động khi ít nhất hai lần nằm trong phạm vi hợp lệ.

### 5.2 Cầu chia áp cho chân Echo

HC-SR04 thường phát Echo mức 5 V, trong khi GPIO ESP32 chỉ chịu khoảng 3,3 V. Không nối Echo trực tiếp vào GPIO19. Dùng hai điện trở, ví dụ:

```text
HC-SR04 ECHO ── 1 kΩ ──┬── GPIO19
                       └── 2 kΩ ── GND
```

Cách mắc này hạ mức 5 V xuống khoảng 3,3 V. Chân `TRIG` từ ESP32 có thể nối trực tiếp vào GPIO18.

### 5.3 Giới hạn và cách kiểm tra

- HC-SR04 không chống nước; chỉ phù hợp sa bàn trong nhà và phải đặt phía trên mặt nước.
- Mặt nước cần nằm trong vùng đo và tương đối phẳng; bọt, thành bể hoặc góc lắp lệch có thể gây mất Echo.
- Không để đầu dò hoặc mạch chạm nước.

Kiểm tra bằng cách cấp 5 V, dùng chung GND, mở Serial Monitor và di chuyển một mặt phẳng trước đầu dò. `distance_cm` phải thay đổi ổn định; LED cảm biến nước chỉ sáng khi firmware nhận ít nhất 2/3 xung Echo hợp lệ. Sau đó đo chiều cao lắp thực tế và cập nhật `SENSOR_MOUNT_HEIGHT_CM`.

## 6. Cảm biến mưa hình tròn

### 6.1 Trạng thái nhận dạng

Dựa trên hình dáng, thiết bị có nhiều đặc điểm của cảm biến mưa quang học công nghiệp. Tuy nhiên chưa có ảnh tem model hoặc datasheet, nên chưa được khẳng định điện áp, pinout và register map.

Các thiết bị có ngoại hình gần giống nhau vẫn có thể sử dụng điện áp và giao thức khác nhau.

### 6.2 Nguyên lý quang học thường gặp

Bên trong cảm biến thường có:

- Nguồn sáng hoặc LED hồng ngoại.
- Bộ thu ánh sáng.
- Các bề mặt quang trong suốt.
- Bộ xử lý tín hiệu.

Khi bề mặt khô, ánh sáng truyền hoặc phản xạ theo trạng thái ổn định. Khi giọt nước rơi lên bề mặt, đường đi và cường độ ánh sáng thay đổi. Bộ xử lý dùng sự thay đổi này để phát hiện mưa hoặc ước lượng lượng mưa.

### 6.3 Dữ liệu có thể cung cấp

Tùy model, cảm biến có thể trả về:

- Trạng thái có mưa/không mưa.
- Lượng mưa tích lũy, đơn vị mm.
- Cường độ mưa, đơn vị mm/min.
- Cường độ mưa, đơn vị mm/h.
- Trạng thái lỗi hoặc trạng thái thiết bị.

Không sử dụng register của một thiết bị khác chỉ vì hình dáng giống nhau.

### 6.4 Cơ chế hỏi–đáp Modbus

Cảm biến thường không tự gửi dữ liệu liên tục. ESP32 đóng vai trò master/client và chủ động truy vấn:

```text
ESP32: thiết bị địa chỉ 1, đọc register X
Cảm biến: register X có giá trị 23
ESP32: áp dụng scale 0,1 → kết quả 2,3 mm
```

Muốn đọc được cần biết đúng:

- Slave ID.
- Baud rate.
- Parity và stop bit.
- Function code.
- Địa chỉ register.
- Hệ số scale.
- Ý nghĩa của giá trị: tổng lượng mưa hay cường độ mưa.

### 6.5 Cách kiểm tra

1. Đọc tem và xác nhận nguồn cùng màu dây.
2. Nối A–A, B–B và GND/COM nếu datasheet yêu cầu.
3. Cấp đúng nguồn cho cảm biến.
4. ESP32 gửi truy vấn Modbus đúng cấu hình.
5. Kiểm tra LED TX của module chớp.
6. Kiểm tra LED RX chớp khi cảm biến phản hồi.
7. Firmware phải nhận đủ frame và kiểm tra CRC đúng.
8. Nhỏ nước có kiểm soát và kiểm tra giá trị thay đổi hợp lý.

Không thể dùng lệnh `ping` để kiểm tra cảm biến RS485 vì nó không phải thiết bị mạng IP.

## 7. Module TTL TO RS485 màu trắng

Module này là bộ chuyển đổi tín hiệu, không phải cảm biến và không phải bộ chuyển nguồn.

### 7.1 Phía TTL nối ESP32

| Module | ESP32 |
|---|---|
| `VCC` | `3V3` |
| `GND` | `GND` |
| `RX` | `GPIO17 / TX2` |
| `TX` | `GPIO16 / RX2` |

TX của ESP32 phải đi vào RX của module; TX của module phải đi vào RX của ESP32.

### 7.2 Phía RS485 nối cảm biến

| Module | Cảm biến mưa |
|---|---|
| `485A` | `A` hoặc `A+` |
| `485B` | `B` hoặc `B-` |
| `GND/SGND` | `GND/COM` nếu datasheet yêu cầu |

ESP32 sử dụng UART TTL mức 3,3 V. Cảm biến sử dụng tín hiệu vi sai giữa hai dây A/B. Không được nối A/B trực tiếp vào GPIO16/17.

### 7.3 Dữ liệu module tạo ra

Module không tạo ra đơn vị `mm`, `cm` hoặc `mm/h`. Nó chỉ chuyển các byte UART thành tín hiệu RS485 và chuyển tín hiệu RS485 nhận được trở lại thành byte UART.

ESP32 vẫn phải thực hiện:

1. Tạo request Modbus.
2. Kiểm tra slave ID và function code.
3. Kiểm tra CRC.
4. Ghép byte thành giá trị register.
5. Áp dụng hệ số scale.

### 7.4 Ý nghĩa LED

| LED | Ý nghĩa |
|---|---|
| `PW` | Module đang có nguồn |
| `TX` | Có dữ liệu truyền theo một hướng |
| `RX` | Có dữ liệu nhận theo hướng còn lại |

`PW` sáng chỉ chứng minh module có nguồn. Giao tiếp chỉ được xác nhận khi TX/RX hoạt động và firmware nhận được frame đúng CRC.

### 7.5 Công tắc 120R

Điện trở 120 Ω dùng để giảm phản xạ tín hiệu ở đầu cuối đường truyền RS485.

- Module nằm ở đầu vật lý của bus: có thể bật.
- Dây thử rất ngắn: có thể chưa cần bật.
- Bus dài: thường đặt điện trở tại hai đầu vật lý.
- Không bật điện trở 120 Ω tại mọi thiết bị trên bus.

## 8. Cặp dây RS485 A/B

Kết nối thông thường:

```text
Module 485A → cảm biến A
Module 485B → cảm biến B
```

Một số nhà sản xuất sử dụng tên `A+/B-`, `D+/D-` hoặc quy ước A/B ngược nhau. Nếu cảm biến không phản hồi:

1. Kiểm tra nguồn cảm biến.
2. Kiểm tra slave ID, baud, parity và register.
3. Kiểm tra GND/COM.
4. Đối chiếu datasheet.
5. Sau cùng mới thử đổi A/B.

Không thay đổi dây khi hệ thống đang cấp nguồn.

## 9. Wi-Fi

Wi-Fi chỉ kết nối ESP32 với backend. Cảm biến nước và cảm biến mưa không kết nối Wi-Fi trực tiếp.

```text
Cảm biến → dây điện → ESP32 → Wi-Fi → backend
```

ESP32 thông thường sử dụng Wi-Fi 2,4 GHz. Một SSID chỉ phát trên 5 GHz có thể không được ESP32 phát hiện.

### Kiểm tra Wi-Fi

- Serial Monitor báo đã kết nối.
- ESP32 nhận được địa chỉ IP.
- LED Wi-Fi sáng.
- `http://<IP-ESP32>/health` trả `wifi.connected=true`.

## 10. Backend

ESP32 gửi HTTP `POST /api/v2/telemetry` với dữ liệu dạng:

```json
{
  "schema_version": 1,
  "device_id": "mini-flood-station-01",
  "boot_id": "ma-khoi-dong",
  "sequence_no": 123,
  "timestamp": "2026-10-22T13:30:00+07:00",
  "rain_interval_mm": 0.05,
  "rain_rate_mmh": 36.0,
  "water_level_cm": 12.5,
  "quality_flags": []
}
```

Backend thực hiện:

- Xác thực thiết bị.
- Chống ghi trùng bằng `boot_id + sequence_no`.
- Lưu telemetry.
- Tính lượng mưa tích lũy trong 5 phút.
- Tính mức thay đổi mực nước trong 2 phút.
- Dự báo mực nước T+15 và T+30.
- So sánh với ngưỡng động.
- Cập nhật dashboard và gửi Telegram.

## 11. Model AI

Model AI không đọc trực tiếp xung Echo hoặc khung RS485. Nó chỉ sử dụng dữ liệu đã được ESP32 và backend chuẩn hóa:

```text
rain_rate_mmh
rain_sum_5m
water_level_cm
water_rise_2m_cm
```

Đầu ra của model:

```text
forecast_15m_cm
forecast_30m_cm
```

AI không tự quyết định An toàn/Cảnh báo/Nguy hiểm. Backend lấy giá trị lớn nhất trong mực nước hiện tại và hai dự báo:

```text
effective_level = max(water_level_cm, forecast_15m_cm, forecast_30m_cm)
```

Sau đó so sánh với cấu hình trạm. Với cấu hình mặc định:

- Dưới 30 cm: An toàn.
- Từ 30 cm đến dưới 40 cm: Cảnh báo.
- Từ 40 cm trở lên: Nguy hiểm.

Các giá trị này có thể thay đổi trên dashboard mà không cần nạp lại ESP32 hoặc huấn luyện lại model.

## 12. Ý nghĩa của các trạng thái LED

| LED | Sáng khi |
|---|---|
| Wi-Fi, GPIO25 | ESP32 đã có kết nối Wi-Fi |
| Backend, GPIO26 | Lần POST gần nhất nhận HTTP 2xx |
| LED mực nước, GPIO27 | HC-SR04 có ít nhất 2/3 xung Echo hợp lệ |
| Mưa, GPIO33 | Nhận được frame Modbus đúng CRC |
| D2 | Tất cả các cụm đang sẵn sàng |

LED D2:

- Sáng liên tục: toàn bộ cụm đạt.
- Một chớp chậm: Wi-Fi hoặc backend lỗi.
- Hai chớp nhanh: mạng hoạt động nhưng có cảm biến chưa đạt.

Đây là LED chẩn đoán thiết bị, không phải LED trạng thái An toàn/Cảnh báo/Nguy hiểm.

## 13. Tiêu chí xác nhận toàn hệ thống hoạt động

| Cụm | Tiêu chí đạt |
|---|---|
| Nguồn | Điện áp đúng, không nóng, không reset lặp |
| ESP32 | Cổng COM xuất hiện và có log boot |
| Firmware | Log báo đúng `real_hardware` |
| Wi-Fi | Có IP và `wifi.connected=true` |
| Backend | HTTP trả 2xx và LED backend sáng |
| Cảm biến nước | Khoảng cách HC-SR04 thay đổi ổn định; ít nhất 2/3 lần đo hợp lệ |
| RS485 | PW sáng, TX/RX chớp khi truy vấn |
| Cảm biến mưa | Có nhiều phản hồi liên tiếp với CRC đúng |
| Dashboard | Hiển thị bản ghi mới từ thiết bị |
| Database | Có telemetry mới với đúng `device_id` |

## 14. Thông tin còn thiếu

Để hoàn thiện driver cảm biến mưa cần:

1. Ảnh rõ tem model hoặc đáy cảm biến.
2. Ảnh toàn bộ dây và màu dây.
3. Điện áp cấp nguồn.
4. Slave ID mặc định.
5. Baud rate và parity.
6. Function code, register và scale.

Khi chưa có các thông tin này, firmware `real_hardware` giữ RS485 ở trạng thái chưa cấu hình và gắn cờ chất lượng thay vì tạo số liệu giả.
