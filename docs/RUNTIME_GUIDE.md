# Chạy model, Backend và dashboard

Bản này chỉ nhận dữ liệu và dự báo, không có lệnh training/generator. Model đã nằm ở `models/current`.

## 1. Cài và chạy BE

Python >=3.11. Thư viện nạp model được pin theo bundle hiện tại.

```powershell
python -m pip install -r requirements.txt
$env:MINI_FLOOD_MODE = "demo"
$env:MINI_FLOOD_AI_CONFIG = "config/ai.demo.json"
$env:MINI_FLOOD_MODEL_DIR = "models/current"
$env:MINI_FLOOD_DB = "mini_flood_demo.sqlite3"
$env:MINI_FLOOD_DEFAULT_DEVICE_ID = "mini-flood-demo"
$env:MINI_FLOOD_DEVICE_KEY = "your-device-key"
$env:MINI_FLOOD_NOTIFICATION_WORKER = "0"
$env:MINI_FLOOD_MDNS_ENABLED = "0"
python -m uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
```

Mode demo là bắt buộc cho bundle đang có vì nguồn training là synthetic. Giữ nhãn nguồn, không sửa metadata promoted. Mode real mặc định từ chối bundle synthetic.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v2/health
```

Kiểm tra `model_ready=true`, `forecast_horizons_seconds=[15,30,60]`, `data_source=synthetic`. Nếu sai hash/schema/library, sửa cấu hình/dependency hoặc thay đúng bundle; không có fallback.

## 2. Chạy dashboard

Trong terminal khác, đặt cùng key/device/mode/config như terminal BE rồi chạy:

```powershell
$env:MINI_FLOOD_API_BASE = "http://127.0.0.1:8000/api/v2"
streamlit run app_mini_flood_dashboard.py
```

Mở http://127.0.0.1:8501. Chọn đúng device ID và bật tự động làm mới. Dashboard hiển thị số đo, forecast 15/30/60 giây, cảnh báo, tuổi dữ liệu và trạng thái AI.

Nếu đang dùng phiên manual đã mở ở 8010/8511, giữ API_BASE tương ứng; không chạy thêm hai BE trên cùng cổng hoặc hai nguồn telemetry cho cùng thiết bị.

## 3. Cấu hình trạm

Ngưỡng demo 30/40 cm chỉ là cấu hình bể ảo, không áp dụng nguyên cho địa điểm thật.

```powershell
$api = "http://127.0.0.1:8000/api/v2"
$headers = @{ "X-Device-Key" = $env:MINI_FLOOD_DEVICE_KEY }
$station = @{
    overflow_level_cm = 40
    warning_margin_cm = 10
    hysteresis_cm = 2
    recovery_hold_seconds = 10
} | ConvertTo-Json
Invoke-RestMethod "$api/stations/mini-flood-demo/config" -Method Put -Headers $headers -ContentType "application/json" -Body $station
```

Hoặc cập nhật bằng form cấu hình ngưỡng trên dashboard. Với IoT thật, dùng đúng device ID của thiết bị và các ngưỡng đã hiệu chuẩn.

## 4. Gửi dữ liệu

IoT gọi POST `/api/v2/telemetry`, header `X-Device-Key`. Các số đo cần có:

- `rain_rate_mmh`: cường độ mưa hiện tại, mm/h.
- `rain_interval_mm`: lượng mưa trong khoảng đo, mm; không gửi counter tích lũy vào trường này.
- `water_level_cm`: mực nước theo mốc đã hiệu chuẩn, cm.
- `timestamp`: giờ đo có timezone, `device_id`, `boot_id`, `sequence_no`, `quality_flags`.
- Schema v2 thêm `sample_interval_ms`; v1 vẫn nhận.

Model hiện tại cần lịch sử hợp lệ cùng boot theo nhịp 5 giây. BE tự tính tổng mưa 15 giây và độ dâng nước 10 giây, thường bắt đầu sau bốn mẫu ở giây 0/5/10/15. Sau đó mỗi mẫu mới hợp lệ đều tạo forecast mới. Thiếu/lỗi/gap/clock sai thì trả null và lý do; dữ liệu cũ không thay live.

Nếu muốn kiểm tra HTTP mà chưa nối IoT, chạy đoạn sau. Đây là mẫu kiểm tra hợp đồng dữ liệu, không phải bộ mô phỏng vật lý:

```powershell
$boot = "manual-" + [guid]::NewGuid().ToString("N")
for ($seq = 0; $seq -lt 4; $seq++) {
    $payload = @{
        schema_version = 2
        device_id = "mini-flood-demo"
        boot_id = $boot
        sequence_no = $seq
        timestamp = [DateTimeOffset]::UtcNow.ToString("o")
        sample_interval_ms = 5000
        sample_age_ms = 0
        rain_interval_mm = 0.05
        rain_rate_mmh = 36
        water_level_cm = 10
        quality_flags = @()
    } | ConvertTo-Json
    Invoke-RestMethod "$api/telemetry" -Method Post -Headers $headers -ContentType "application/json" -Body $payload
    if ($seq -lt 3) { Start-Sleep -Seconds 5 }
}
Invoke-RestMethod "$api/stations/mini-flood-demo/snapshot" -Headers $headers
```

ACK chỉ báo accepted/duplicate/quality/server time. Forecast đọc trong snapshot, latest/history hoặc stream; không trả model output cho ESP32.

## 5. Cảnh báo và Telegram

BE xét forecast lớn nhất: <30 cm là chưa dự báo vượt ngưỡng; 30–<40 cm cảnh báo; ≥40 cm nguy hiểm. Nước hiện tại mới và hợp lệ ≥40 cm kích hoạt sensor_rule riêng. Model/dữ liệu thiếu không tự kết luận an toàn hoặc hạ mức cũ. Recovery cần hysteresis và thời gian giữ.

Mặc định worker tắt trong ví dụ. Khi cần Telegram, cấu hình token/chat ID qua môi trường, bật worker rồi restart BE:

```powershell
$env:MINI_FLOOD_TELEGRAM_TOKEN = "your-token"
$env:MINI_FLOOD_TELEGRAM_CHAT_ID = "your-chat-id"
$env:MINI_FLOOD_NOTIFICATION_WORKER = "1"
```

Chỉ gửi sự kiện nâng/hạ mức, nhắc và sức khỏe thiết bị; không gửi mỗi forecast. Không commit token.

## 6. Bảo trì

- Không đổi cửa sổ/đơn vị/schema mà giữ nguyên artifact khác contract. Muốn đổi model, cung cấp bundle mới tương thích và đã đánh giá ở quy trình bên ngoài runtime.
- Model hiện tại đã kiểm thử trên synthetic; chưa nghiệm thu độ chính xác IoT thật hoặc SLA Telegram thật.
- Runtime giữ payload v1/v2, migration và dữ liệu lịch sử.
- Code training, dataset và bundle thử nghiệm được lưu local tại archive/ai_training, không được runtime import hoặc pytest thu thập.
- Test runtime: cài requirements-dev.txt rồi chạy `pytest -q`. Có test trực tiếp bundle models/current, không gọi pipeline training.
- Firmware source hiện là V3/schema v2 với cadence 10 giây. Cadence này chưa khớp
  profile model demo 5 giây; xem
  [phân tích cập nhật IoT V3](PHAN_TICH_CAP_NHAT_IOT_V3.md) trước khi nối thiết bị thật.
