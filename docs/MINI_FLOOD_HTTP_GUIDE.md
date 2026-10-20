# Prototype mô hình mini dự báo ngập 15/30 phút

> **MÔ PHỎNG THỬ NGHIỆM:** hệ thống này kiểm chứng luồng AI + IoT trên mô hình vật lý thu nhỏ. Kết quả chưa phải cảnh báo vận hành cho Hội An.

## 1. Thành phần

- `mini_flood_api.py`: FastAPI nhận HTTP từ ESP32.
- `mini_flood/`: SQLite, feature engine, model registry và cảnh báo.
- `app_mini_flood_dashboard.py`: dashboard Streamlit.
- `train_mini_flood_models.py`: tạo nhãn, chia theo lần thí nghiệm và huấn luyện model 15/30 phút.
- `firmware/esp32_http/mini_flood_station.ino`: firmware ESP32 mẫu.

Khi chưa có model 15/30 phút được huấn luyện, backend tự dùng baseline theo quy tắc ngưỡng và ghi version `mini-flood-baseline-v1`.

## 2. Cấu hình

PowerShell:

```powershell
$env:MINI_FLOOD_DEVICE_KEY = "replace-with-a-long-random-key"
$env:MINI_FLOOD_DB = "mini_flood.sqlite3"
$env:MINI_FLOOD_WARNING_CM = "15"
$env:MINI_FLOOD_DANGER_CM = "25"
```

Cấu hình Telegram và email nếu cần:

```powershell
$env:MINI_FLOOD_TELEGRAM_TOKEN = "..."
$env:MINI_FLOOD_TELEGRAM_CHAT_ID = "..."
$env:MINI_FLOOD_SMTP_HOST = "smtp.example.com"
$env:MINI_FLOOD_SMTP_PORT = "587"
$env:MINI_FLOOD_SMTP_USERNAME = "..."
$env:MINI_FLOOD_SMTP_PASSWORD = "..."
$env:MINI_FLOOD_EMAIL_FROM = "..."
$env:MINI_FLOOD_EMAIL_TO = "person1@example.com,person2@example.com"
```

Không lưu các giá trị bí mật vào Git.

## 3. Chạy hệ thống

```powershell
pip install -r requirements.txt
uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
```

Mở dashboard ở terminal khác:

```powershell
streamlit run app_mini_flood_dashboard.py
```

Kiểm tra API:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health
```

Gửi telemetry mẫu:

```powershell
$headers = @{ "X-Device-Key" = $env:MINI_FLOOD_DEVICE_KEY }
$body = @{
  schema_version = 1
  device_id = "mini-flood-station-01"
  sequence_no = 1
  timestamp = (Get-Date).ToString("o")
  rain_interval_mm = 0.5
  rain_rate_mmh = 30.0
  water_level_cm = 12.0
  quality_flags = @()
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/telemetry -Headers $headers -ContentType "application/json" -Body $body
```

API trả `warming_up` cho đến khi có tối thiểu 15 phút lịch sử. Nếu mực nước vượt ngưỡng nguy hiểm, luật an toàn vẫn cảnh báo ngay.

Phản hồi HTTP chỉ xác nhận bản ghi đã được nhận:

```json
{
  "accepted": true,
  "duplicate": false,
  "quality_status": "valid",
  "server_timestamp": "2026-10-18T10:00:00Z"
}
```

Dự báo không được gửi ngược về ESP32. Dashboard và hệ thống thông báo đọc kết quả đã lưu trong backend.

Trước mỗi lần chạy mô hình, đăng ký mã thí nghiệm và loại kịch bản:

```powershell
$experiment = @{
  device_id = "mini-flood-station-01"
  experiment_id = "normal-run-01"
  scenario = "normal"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/experiments/start -Headers $headers -ContentType "application/json" -Body $experiment
```

`scenario` nhận một trong ba giá trị: `normal`, `warning`, `danger`. ESP32 không cần gửi trường này trong từng payload; backend tự gắn thí nghiệm đang hoạt động. Khi kết thúc:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/experiments/stop?device_id=mini-flood-station-01" -Headers $headers
```

Xuất CSV để train:

```powershell
Invoke-WebRequest "http://localhost:8000/api/v1/experiments/export.csv?device_id=mini-flood-station-01" -Headers $headers -OutFile telemetry_experiments.csv
```

## 4. Kết nối ESP32

Trong `firmware/esp32_http/mini_flood_station.ino`, đổi:

- `API_URL` thành IP LAN của laptop, ví dụ `http://192.168.1.100:8000/api/v1/telemetry`.
- `DEVICE_KEY` khớp với `MINI_FLOOD_DEVICE_KEY`.
- Wi-Fi SSID và mật khẩu khi dùng mạch thật.

Firmware giữ tối đa 100 bản ghi trong RAM và gửi lại khi Wi-Fi hoạt động. `sequence_no` được lưu trong NVS để hạn chế trùng sau khi mất nguồn.

Firmware không đọc cấp cảnh báo từ response và không điều khiển LED hoặc còi.

Wokwi dùng biến trở để giả lập mưa. Cảm biến mưa RS485 thật cần được thay bằng hàm đọc Modbus theo đúng datasheet, địa chỉ thanh ghi và hệ số quy đổi của thiết bị.

## 5. Thu thập và train model

Mỗi lần chạy thí nghiệm phải có `experiment_id` trong CSV xuất dùng để train. Các cột bắt buộc:

```text
experiment_id,device_id,sequence_no,timestamp,rain_interval_mm,rain_rate_mmh,water_level_cm,quality_flags
```

Chạy ít nhất ba lần cho mỗi kịch bản Bình thường, Cảnh báo và Nguy hiểm, sau đó:

```powershell
python train_mini_flood_models.py --input telemetry_experiments.csv
```

Script:

- Tạo feature chỉ từ dữ liệu quá khứ.
- Chỉ sử dụng `rain_rate_mmh`, `rain_sum_5m`, `water_level_cm` và `water_rise_2m_cm`.
- Tạo nhãn bằng mực nước tương lai 15/30 phút.
- Chia train/test theo `experiment_id` và thời gian.
- Huấn luyện Multinomial Logistic Regression và so sánh với baseline.
- Chỉ lưu model học máy khi Macro-F1 tốt hơn baseline và Recall nguy hiểm không thấp hơn baseline.
- Xuất benchmark, metadata và hai confusion matrix trong `models/`.

Khởi động lại API sau khi train để nạp model mới.

## 6. Kiểm thử

```powershell
pytest -q
```

Bộ test bao gồm schema HTTP, xác thực khóa, chống trùng, warm-up, safety override, feature theo cửa sổ thời gian, cooldown bền vững và retry độc lập Telegram/email.
