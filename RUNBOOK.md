# Runbook Mini Flood AI V1

## 1. Cài đặt

```powershell
cd D:\Projects\tool-craw
python -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 2. Cấu hình tối thiểu

```powershell
$env:MINI_FLOOD_DEVICE_KEY = "replace-with-a-long-random-key"
$env:MINI_FLOOD_DB = "mini_flood.sqlite3"
$env:MINI_FLOOD_WARNING_CM = "15"
$env:MINI_FLOOD_DANGER_CM = "25"
```

Không commit token hoặc mật khẩu vào Git.

## 3. Chạy backend

```powershell
python -m uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
```

Kiểm tra:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health
```

## 4. Chạy dashboard

Trong terminal khác:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run app_mini_flood_dashboard.py
```

Dashboard đọc trực tiếp cùng file SQLite với backend.

## 5. Kết nối ESP32

Mở [`firmware/esp32_http/mini_flood_station.ino`](firmware/esp32_http/mini_flood_station.ino) và sửa:

- `WIFI_SSID`
- `WIFI_PASSWORD`
- `API_URL`
- `DEVICE_KEY`

ESP32 chỉ gửi dữ liệu và kiểm tra HTTP thành công hay thất bại. Thiết bị không nhận cấp cảnh báo hoặc lệnh điều khiển từ backend.

## 6. Thu thập thí nghiệm

Trước mỗi lần chạy, gọi `POST /api/v1/experiments/start` với một trong ba scenario:

- `normal`
- `warning`
- `danger`

Mỗi lần chạy nên dài ít nhất 46 phút ở chu kỳ một phút để có 15 phút lịch sử và 30 phút dữ liệu tương lai. Thực hiện ít nhất ba lần cho mỗi scenario.

Xuất dữ liệu:

```powershell
$headers = @{ "X-Device-Key" = $env:MINI_FLOOD_DEVICE_KEY }
Invoke-WebRequest `
  "http://localhost:8000/api/v1/experiments/export.csv?device_id=mini-flood-station-01" `
  -Headers $headers `
  -OutFile telemetry_experiments.csv
```

## 7. Huấn luyện

```powershell
python train_mini_flood_models.py --input telemetry_experiments.csv --output-dir models
```

Script chỉ huấn luyện Multinomial Logistic Regression, so sánh với baseline và chỉ lưu model khi:

- Macro-F1 cao hơn baseline.
- Recall lớp Nguy hiểm không thấp hơn baseline.
- Tập train có đủ cả ba lớp.

Đầu ra:

- `models/mini_flood_15m.joblib`
- `models/mini_flood_30m.joblib`
- `models/mini_flood_metadata.json`
- `models/mini_flood_benchmark.csv`
- `models/mini_flood_confusion_matrices.png`

## 8. Telegram và email

Chi tiết quy trình thu thập dữ liệu thật, cấu hình BotFather và kịch bản cảnh báo xem tại:  
[Kế hoạch Train Dữ Liệu Thật & Cảnh Báo Telegram](docs/KE_HOACH_TRAIN_DU_LIEU_THAT_VA_CANH_BAO_TELEGRAM.md).

Telegram:

```powershell
$env:MINI_FLOOD_TELEGRAM_TOKEN = "..."
$env:MINI_FLOOD_TELEGRAM_CHAT_ID = "..."
```

Kiểm tra nhanh kết nối Telegram mà không cần chạy server:

```powershell
python test_telegram_ping.py
```

Email:

```powershell
$env:MINI_FLOOD_SMTP_HOST = "smtp.example.com"
$env:MINI_FLOOD_SMTP_PORT = "587"
$env:MINI_FLOOD_SMTP_USERNAME = "..."
$env:MINI_FLOOD_SMTP_PASSWORD = "..."
$env:MINI_FLOOD_EMAIL_FROM = "..."
$env:MINI_FLOOD_EMAIL_TO = "person@example.com"
```

## 9. Kiểm thử

```powershell
pytest -q
```

## 10. Xử lý sự cố

| Hiện tượng | Kiểm tra |
|---|---|
| API trả `401` | `X-Device-Key` phải khớp `MINI_FLOOD_DEVICE_KEY` |
| API trả `warming_up` | Cần tối thiểu 15 phút lịch sử |
| Dashboard chưa có dữ liệu | Backend và dashboard phải dùng cùng `MINI_FLOOD_DB` |
| `model_ready=false` | Chưa có đủ hai model V1 hợp lệ trong `models/` |
| Không nhận thông báo | Kiểm tra biến môi trường Telegram/SMTP và bảng `delivery_attempts` |
| ESP32 mất Wi-Fi | Dữ liệu được lưu đệm; trong thời gian đó backend không thể cảnh báo theo dữ liệu mới |

## 11. Giới hạn
 
Hệ thống V1 được thiết kế chuyên biệt cho mô hình thực nghiệm mini flood cục bộ (chu kỳ 1 phút, dự báo 15/30 phút). Toàn bộ pipeline cũ đã được dọn dẹp để tập trung hoàn toàn vào pipeline Mini Flood V1.
