# Thiết bị và quy trình kiểm tra phần cứng thật

## 1. Kết luận nhanh

Hệ thống gồm hai loại đường dữ liệu khác nhau:

1. Cảm biến mực nước HC-SR04 đo **khoảng cách siêu âm**; ESP32 điều khiển `TRIG` tại GPIO18 và nhận `ECHO` tại GPIO19 qua cầu chia áp.
2. Cảm biến mưa dạng tròn nhiều khả năng là cảm biến quang có giao tiếp **RS485**; ESP32 phải gửi lệnh và nhận khung dữ liệu qua module TTL–RS485.

Module TTL–RS485 chỉ chuyển mức điện và kiểu đường truyền. Nó không tự đo mưa, không đổi nguồn 12 V xuống 3,3 V và không tự biến dữ liệu thành `mm/h`.

Profile `real_hardware` đã tách chân rõ ràng: HC-SR04 dùng GPIO18/19 và UART2 của RS485 dùng GPIO16/17. Trang `/health` báo riêng trạng thái Wi-Fi, backend, HC-SR04 và phản hồi Modbus. Đèn nguồn sáng chỉ chứng minh bo được cấp điện; chưa chứng minh cảm biến thật đã được đọc.

## 2. ESP32 và bo mở rộng

### Chức năng

ESP32 là bộ điều khiển trung tâm:

- Phát xung Trig và đo xung Echo của HC-SR04.
- Gửi lệnh Modbus tới cảm biến mưa và kiểm tra phản hồi.
- Quy đổi dữ liệu thô thành đơn vị kỹ thuật.
- Kết nối Wi-Fi và gửi JSON tới backend.
- Lưu tạm tối đa 100 bản ghi trong RAM nếu mất mạng.

UART0 qua USB dùng để nạp chương trình và xem log. UART phụ dùng `GPIO16` và `GPIO17` cho cảm biến RS485.

### Dữ liệu ESP32 nhận

- Từ cảm biến nước: độ rộng xung Echo, được đổi thành khoảng cách tới mặt nước và `water_level_cm`.
- Từ cảm biến mưa: chuỗi byte của khung trả lời Modbus, chỉ có ý nghĩa khi biết đúng địa chỉ thiết bị, baud rate, parity, thanh ghi và hệ số scale.

### Kiểm tra đạt

1. Cắm USB dữ liệu vào máy tính.
2. Cổng COM mới phải xuất hiện.
3. Mở Serial Monitor ở `115200` baud.
4. Nhấn EN/RESET; phải thấy dòng `[BOOT] Mini Flood firmware V2`.
5. Sau khi vào Wi-Fi phải thấy IP và có thể mở `http://<IP-ESP32>/health`.

Số cổng COM có thể thay đổi khi đổi cổng USB hoặc máy tính. Chọn đúng cổng vừa xuất hiện khi cắm ESP32; không cố định `COM6` trong cấu hình dùng chung.

## 3. Adapter DC và bo cấp nguồn

### Chức năng

Adapter biến điện lưới AC thành điện DC để cấp cho bo mở rộng. Mạch ổn áp trên bo mở rộng sau đó tạo mức điện phù hợp cho ESP32.

### Kiểm tra trước khi cắm

- Đọc nhãn adapter: điện áp DC, dòng tối đa và cực tính đầu jack.
- Dùng đồng hồ đo điện áp tại đầu jack.
- Đối chiếu điện áp đầu vào được in trên bo mở rộng.
- Không suy ra bo chấp nhận 12 V chỉ vì đầu jack cắm vừa.

### Kiểm tra đạt

- Điện áp đo đúng nhãn và đúng cực tính.
- LED nguồn của bo sáng ổn định.
- ESP32 không nóng bất thường và không reset lặp lại.

## 4. Module TTL TO RS485 màu trắng

### Chức năng

Đây là bộ chuyển đổi cách ly TTL sang RS485, loại half-duplex:

- Phía ESP32: `VCC`, `GND`, `TX`, `RX`.
- Phía bus: `485A`, `485B`, `GND/SGND`.
- LED `PW`: có nguồn.
- LED `TX`: có dữ liệu truyền.
- LED `RX`: có dữ liệu nhận.
- Công tắc `120R`: bật điện trở kết thúc đường truyền.

Nhà sản xuất công bố nguồn module là `3,3–5 V`; vì vậy có thể cấp `3V3` từ ESP32. Không cấp 12 V vào `VCC`.

### Dữ liệu module đưa về ESP32

Module không đưa ra `mm`, `cm` hay `mm/h`. Nó chuyển tín hiệu vi sai A/B thành các byte UART tại chân `TX`. Phần mềm ESP32 phải:

1. Kiểm tra địa chỉ slave và mã hàm.
2. Kiểm tra độ dài và CRC.
3. Ghép byte thành giá trị thanh ghi.
4. Nhân/chia theo hệ số scale trong tài liệu cảm biến.

### Kiểm tra đạt

- `PW` sáng khi cấp 3,3 V.
- Khi ESP32 gửi truy vấn, LED `TX` chớp.
- Khi cảm biến phản hồi, LED `RX` chớp.
- ESP32 nhận đủ khung, đúng slave ID, function code và CRC.

Chỉ thấy `PW` sáng nhưng không có `TX/RX` nghĩa là module có nguồn nhưng chưa chứng minh truyền thông hoạt động.

## 5. Cảm biến mưa dạng tròn

### Nhận dạng hiện tại

Hình dáng rất giống cảm biến mưa quang học công nghiệp: giọt nước làm thay đổi đường truyền ánh sáng qua các bề mặt quang, mạch điện xử lý sự thay đổi rồi cung cấp lượng mưa qua RS485 hoặc xung.

Tuy nhiên, ảnh hiện tại không cho thấy tem model, màu dây và bảng thanh ghi. Vì vậy chưa được phép khẳng định:

- Điện áp cấp nguồn.
- Dây nào là `V+`, `GND`, `A`, `B`.
- Slave ID, baud, parity.
- Thanh ghi biểu diễn tổng lượng mưa hay cường độ mưa.
- Đơn vị và hệ số scale.

Các cảm biến ngoại hình gần giống nhau có thể dùng nguồn và register map khác nhau. Cần ảnh rõ tem bên ngoài, đầu dây hoặc tài liệu đi kèm trước khi cấp nguồn.

### Dữ liệu có thể trả về

Tùy model, cảm biến có thể trả một hoặc nhiều giá trị:

- Lượng mưa tích lũy, đơn vị mm.
- Cường độ mưa, đơn vị mm/min hoặc mm/h.
- Trạng thái có mưa/không mưa.
- Trạng thái lỗi hoặc mức tín hiệu.

Đây chỉ là các khả năng phổ biến; không dùng địa chỉ thanh ghi của một model khác để điều khiển thiết bị đang có.

### Kiểm tra đạt

1. Xác nhận tem và cấp đúng nguồn.
2. Nối A–A, B–B và GND/COM nếu tài liệu yêu cầu.
3. ESP32 gửi một truy vấn Modbus đã biết.
4. Cảm biến trả lời đúng CRC liên tiếp ít nhất 10 lần.
5. Nhỏ một lượng nước kiểm soát lên vùng quang; giá trị mưa hoặc trạng thái phải thay đổi hợp lý.
6. Lau khô và kiểm tra giá trị trở về ổn định.

Không dùng `ping` mạng để kiểm tra cảm biến này. Nó không phải thiết bị IP; phép thử đúng là request/response Modbus.

## 6. Cảm biến mực nước HC-SR04

### Chức năng

HC-SR04 phát sóng siêu âm và đo thời gian tiếng dội từ mặt nước. ESP32 tính khoảng cách từ đầu dò tới mặt nước, sau đó tính:

```text
water_level_cm = SENSOR_MOUNT_HEIGHT_CM - distance_cm
```

### Đấu nối và bảo vệ ESP32

| HC-SR04 | ESP32 |
|---|---|
| `VCC` | `5V` |
| `GND` | `GND` chung |
| `TRIG` | `GPIO18` |
| `ECHO` | `GPIO19` qua cầu chia áp |

Echo của HC-SR04 thường là 5 V, cao hơn mức an toàn của GPIO ESP32. Dùng cầu chia áp, ví dụ `1 kΩ` từ Echo tới GPIO19 và `2 kΩ` từ GPIO19 xuống GND, để hạ còn khoảng 3,3 V. Không nối Echo trực tiếp.

### Dữ liệu đưa về ESP32

- Tín hiệu thô: độ rộng xung Echo tính bằng microsecond.
- Dữ liệu chẩn đoán: `distance_cm` và số lần đo hợp lệ.
- Dữ liệu gửi backend: `water_level_cm` không âm.

`SENSOR_MOUNT_HEIGHT_CM` phải được đo từ mặt đầu dò tới đáy bể khi bể rỗng. Giá trị này khác với `overflow_level_cm` do backend quản lý.

### Kiểm tra đạt

1. Đặt đầu dò phía trên, vuông góc với mặt nước; không để mạch chạm nước.
2. Mở Serial Monitor rồi di chuyển một mặt phẳng trước đầu dò.
3. `distance_cm` phải thay đổi ổn định và hợp lý.
4. Firmware lấy ba mẫu; cảm biến chỉ được coi là kết nối khi ít nhất hai mẫu hợp lệ.
5. Đo lại chiều cao lắp và cấu hình `SENSOR_MOUNT_HEIGHT_CM` trước khi dùng số `water_level_cm`.

HC-SR04 không chống nước, phù hợp sa bàn trong nhà. Khi dùng ngoài trời nên chuyển sang đầu dò chống nước phù hợp.

## 7. Dữ liệu ESP32 gửi về backend

Sau khi đọc và quy đổi cảm biến, ESP32 gửi HTTP `POST /api/v2/telemetry` với dạng:

```json
{
  "schema_version": 1,
  "device_id": "mini-flood-station-01",
  "boot_id": "<mỗi lần khởi động một mã>",
  "sequence_no": 123,
  "timestamp": "2026-10-22T13:30:00+07:00",
  "rain_interval_mm": 0.05,
  "rain_rate_mmh": 36.0,
  "water_level_cm": 12.5,
  "quality_flags": []
}
```

Ý nghĩa:

| Trường | Nguồn |
|---|---|
| `rain_interval_mm` | Lượng mưa trong đúng khoảng lấy mẫu; có thể lấy trực tiếp từ cảm biến hoặc tính từ cường độ |
| `rain_rate_mmh` | Cường độ mưa đã chuẩn hóa về mm/h |
| `water_level_cm` | Chiều cao lắp HC-SR04 trừ khoảng cách tới mặt nước |
| `quality_flags` | Lỗi timeout, CRC, chưa hiệu chuẩn, dữ liệu ngoài phạm vi... |

Backend mới là nơi tính `rain_sum_5m`, `water_rise_2m_cm`, dự báo T+15/T+30 và trạng thái An toàn/Cảnh báo/Nguy hiểm. ESP32 không nên tự gán trạng thái cảnh báo.

## 8. Tiêu chí nghiệm thu toàn hệ thống

| Cụm | Đạt khi |
|---|---|
| Nguồn | Điện áp đúng, không nóng, không reset lặp |
| USB/ESP32 | Xuất hiện COM và có log boot |
| Wi-Fi | Có IP, `wifi.connected=true` |
| Backend | POST nhận HTTP 2xx, `backend.connected=true` |
| TTL–RS485 | PW sáng; TX và RX chớp khi truy vấn |
| Cảm biến mưa | 10 phản hồi Modbus đúng CRC, giá trị đổi khi thử nước |
| Cảm biến nước | HC-SR04 có ít nhất 2/3 xung Echo hợp lệ; khoảng cách thay đổi ổn định |
| End-to-end | Dashboard hiển thị đúng dữ liệu mới và DB có bản ghi tương ứng |

## 9. Thông tin còn thiếu để hoàn thiện driver

Cần bổ sung ảnh rõ:

1. Tem bên ngoài hoặc đáy cảm biến mưa.
2. Toàn bộ đầu dây và màu dây cảm biến mưa.
3. Nhãn điện áp/dòng/cực tính của adapter.
4. Dòng chữ điện áp đầu vào cạnh jack DC của bo mở rộng.

Khi có bốn thông tin này mới nên sửa firmware và cấp nguồn cho cảm biến mưa.

## Tài liệu tham khảo

- Arduino, hàm `pulseIn()` dùng đo độ rộng xung Echo: https://docs.arduino.cc/language-reference/en/functions/advanced-io/pulseIn/
- Espressif, Serial/UART Arduino-ESP32: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/serial.html
- Spotpear, TTL TO RS485 (B): https://spotpear.cn/index.php/index/study/detail/id/973.html
- Modbus Organization, specifications: https://www.modbus.org/modbus-specifications
