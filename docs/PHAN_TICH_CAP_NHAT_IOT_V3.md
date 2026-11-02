# Phân tích cập nhật IoT V3

Tài liệu này mô tả trạng thái source IoT hiện tại, các thay đổi so với firmware
trước đó và những điều kiện cần xác minh trước khi nạp lên thiết bị thật. Nội dung
được đối chiếu với `EPS32_PROJECT/src/main.cpp`, API và AI runtime ngày
02/11/2026.

## 1. Kết luận nhanh

Luồng IoT đã được nâng từ firmware V2/schema v1 lên firmware V3/schema v2:

```text
HC-SR04 + cảm biến mưa Modbus
             │
             ▼
        ESP32 firmware V3
        - lấy mẫu mỗi 5 giây
        - kiểm tra cảm biến
        - đệm tối đa 100 mẫu
             │ HTTP POST /api/v2/telemetry
             ▼
        FastAPI/backend
        - xác thực và chống trùng
        - kiểm tra thời gian/chất lượng
        - lưu telemetry + inference trace
        - snapshot + cảnh báo
             │
             ├── Dashboard/SSE/WebSocket
             └── Telegram/email worker
```

Firmware, backend và bundle model demo đã thống nhất schema v2 cùng cadence 5
giây. Mỗi board khai báo `MINI_FLOOD_DEVICE_ID`; giá trị này phải trùng mã trạm
backend để telemetry được nhận và xuất hiện đúng trên dashboard.

## 2. Thay đổi trong firmware ESP32

| Hạng mục | Trước | Hiện tại |
|---|---|---|
| Phiên bản log boot | V2 | V3 |
| Chu kỳ lấy mẫu/gửi | 60 giây | 5 giây |
| Telemetry | schema v1 | schema v2 |
| Thời gian mẫu | Chỉ có `timestamp` | Thêm `sample_interval_ms`, `sample_age_ms` |
| Dữ liệu gửi lại từ buffer | Không biểu diễn rõ tuổi mẫu | Có `sample_age_ms` tăng theo thời gian chờ |
| Cấu hình mưa mặc định | Có thể được coi là đã cấu hình | Fail-closed: mặc định chưa xác minh |
| Build kiểm tra | Chỉ `real_hardware` | Thêm `safe_defaults` |

### 2.1 Telemetry schema v2

Payload firmware hiện tại:

```json
{
  "schema_version": 2,
  "device_id": "mini-flood-demo",
  "boot_id": "a1b2c3d4-e5f60708",
  "sequence_no": 123,
  "timestamp": "2026-11-01T10:30:00+07:00",
  "sample_interval_ms": 5000,
  "sample_age_ms": 0,
  "rain_interval_mm": 0.05,
  "rain_rate_mmh": 18.0,
  "water_level_cm": 12.5,
  "quality_flags": []
}
```

- `boot_id + sequence_no` là khóa chống ghi trùng qua từng lần khởi động.
- `sample_interval_ms` là khoảng thời gian thực giữa hai lần lấy mẫu.
- `sample_age_ms` cho biết mẫu đã nằm trong buffer bao lâu trước khi được gửi.
- Mẫu gửi lại vẫn giữ `timestamp` lúc đo; backend không được coi thời điểm nhận là
  thời điểm đo.

### 2.2 Cảm biến mưa chuyển sang fail-closed

`MINI_FLOOD_RAIN_MODBUS_CONFIGURED` mặc định bằng `0`. Trạng thái này cho phép
probe RS485 để kiểm tra đường truyền nhưng không coi register thử nghiệm là số liệu
mưa hợp lệ.

Chỉ đổi thành `1` trong `include/hardware_config.h` sau khi đã xác nhận:

1. Model cảm biến và điện áp cấp.
2. Slave ID, baud, parity và stop bit.
3. Function code và register.
4. Scale và ý nghĩa giá trị: tổng lượng mưa hay cường độ mưa.
5. Nhiều frame liên tiếp có CRC đúng và số liệu thay đổi hợp lý khi thử nước.

### 2.3 Buffer và dữ liệu ngoại tuyến

ESP32 giữ tối đa 100 bản ghi trong RAM. Với cadence 5 giây, buffer tương đương
khoảng 8 phút 20 giây. Khi đầy, bản ghi cũ nhất bị loại. Buffer RAM bị mất khi
ESP32 reset hoặc mất nguồn; đây chưa phải hàng đợi bền vững trên flash.

## 3. Thay đổi trong backend IoT

Backend vẫn nhận schema v1 để tương thích, nhưng firmware V3 gửi schema v2. Với
schema v2, `sample_interval_ms` là bắt buộc.

### 3.1 Kiểm soát chất lượng và thời gian

Backend hiện:

- Chuẩn hóa timestamp về UTC và lưu riêng thời điểm server nhận.
- Gắn `clock_invalid` khi đồng hồ thiết bị chưa hợp lệ hoặc đi quá xa tương lai.
- Gắn `stale_timestamp` cho mẫu quá cũ và `out_of_order` cho mẫu đi ngược thời gian.
- Không cho mẫu cũ, sai thời gian hoặc sai thứ tự thay trạng thái live/cảnh báo.
- Không nối lịch sử qua hai `boot_id` khác nhau để tạo feature giả.
- Từ chối AI khi nước hoặc mưa không hợp lệ; không tự tạo forecast thay thế.

### 3.2 Snapshot và truy vết

`GET /api/v2/stations/{device_id}/snapshot` trả:

- `last_received`: gói mới nhất backend nhận, kể cả gói cũ từ buffer.
- `current_measurement`: số đo live mới nhất hợp lệ.
- `current_inference`: lần đánh giá AI live gần nhất.
- `last_successful_inference`: lần dự báo thành công gần nhất.
- `alert_state`: mức cảnh báo đang được giữ.

Mỗi inference lưu payload gốc, vector feature, cấu hình/hash, model/hash, kết quả,
thời lượng xử lý và lý do quyết định. Điều này giúp truy lại vì sao một cảnh báo
được tạo ra.

### 3.3 Cảnh báo

- `sensor_rule` chỉ được kích hoạt khi mực nước mới, hợp lệ và vượt ngưỡng tràn.
- `model` dùng forecast hợp lệ để nâng cảnh báo sớm.
- Mất model hoặc thiếu lịch sử không tự hạ trạng thái về An toàn.
- Hạ mức cần thỏa hysteresis và thời gian giữ phục hồi.
- Worker kiểm tra cả thiết bị mất dữ liệu và hàng đợi Telegram/email.

## 4. Cadence firmware và model

Ba cấu hình đang tồn tại:

| Thành phần | Cadence | Horizon |
|---|---:|---|
| Firmware ESP32 V3 | 5 giây | Không dự báo tại thiết bị |
| `config/ai.demo.json` | Kỳ vọng 5 giây | 15/30/60 giây |
| `config/ai.json` | Kỳ vọng 60 giây | 5/10/15 phút |

Bundle trong `models/current/` là model synthetic dành cho profile demo 5 giây.
Firmware hiện gửi cùng cadence nên đủ bốn điểm cho cửa sổ 0/5/10/15 giây nếu
timestamp, cảm biến và mạng hợp lệ. Khi đổi cadence phải thay config và model có
feature signature tương ứng; không chỉ tăng `max_gap_seconds` để ép model chạy.

## 5. Tương thích và rủi ro triển khai

| Nội dung | Trạng thái | Hành động |
|---|---|---|
| Schema v1 cũ | Còn được backend nhận | Chỉ dùng cho client cũ |
| Schema v2 firmware | Đã triển khai trong source | Build và test payload thật |
| HC-SR04 | Có driver và kiểm tra 2/3 xung | Hiệu chuẩn chiều cao lắp/vùng mù |
| RS485 probe | Có | Xác nhận response và CRC |
| Dữ liệu mưa hợp lệ | Mặc định tắt | Chỉ bật sau khi đối chiếu datasheet |
| Buffer mất điện | Chưa bền vững | Đánh giá có cần lưu flash hay không |
| Model demo | Synthetic, 5 giây | Không dùng để công bố nghiệm thu thật |
| Cadence firmware/model | Đã khớp 5 giây | Kiểm tra `sample_interval_ms` khi nghiệm thu |

## 6. Checklist nghiệm thu IoT

1. Build `safe_defaults` để xác nhận source không phụ thuộc file cấu hình local.
2. Build `real_hardware` với `secrets.h` và `hardware_config.h` đã rà soát.
3. Serial Monitor phải in firmware V3 và profile `real_hardware`.
4. `/health` trên ESP32 phải phản ánh đúng Wi-Fi, backend và từng cảm biến.
5. Gửi ít nhất 20 mẫu liên tiếp, kiểm tra sequence, timestamp, interval và age.
6. Ngắt Wi-Fi, chờ vài mẫu, kết nối lại và kiểm tra thứ tự dữ liệu buffer.
7. Xác nhận gói buffer không thay `current_measurement` nếu đã quá cũ.
8. Kiểm tra duplicate bằng cách gửi lại cùng `boot_id + sequence_no`.
9. Hiệu chuẩn mực nước và ngưỡng warning/overflow bằng phép đo thực tế.
10. Chỉ nghiệm thu AI khi cadence, config và model artifact cùng một contract.

## 7. File nguồn liên quan

- Firmware: `EPS32_PROJECT/src/main.cpp`
- Cấu hình phần cứng mẫu: `EPS32_PROJECT/include/hardware_config.h.example`
- Cấu hình PlatformIO: `EPS32_PROJECT/platformio.ini`
- Schema HTTP: `mini_flood/schemas.py`
- Ingest và snapshot: `mini_flood/service.py`
- Feature engine: `mini_flood/features.py`
- API: `mini_flood_api.py`
- Cấu hình AI: `config/ai.json`, `config/ai.demo.json`
