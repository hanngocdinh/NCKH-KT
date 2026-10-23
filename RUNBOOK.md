# Runbook Mini Flood AI V2

## 1. Khởi chạy

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:MINI_FLOOD_DEVICE_KEY = "replace-with-a-long-random-key"
python -m uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
```

Kiểm tra:

```powershell
Invoke-RestMethod http://localhost:8000/api/v2/health
```

Dashboard:

```powershell
streamlit run app_mini_flood_dashboard.py
```

## 2. Cấu hình mạng cho ESP32 thật

### 2.1. Cơ chế tự tìm backend

Firmware `real_hardware` không ghi cứng địa chỉ `192.168.1.x`. Backend quảng bá
service `_mini-flood._tcp.local` với tên ổn định:

```text
mini-flood-backend.local
```

Sau khi kết nối Wi-Fi, ESP32 tìm service này, lấy IP/port hiện tại của laptop và
lưu URL gần nhất trong `Preferences`. Nếu laptop đổi IP và HTTP lỗi, ESP32 xóa
URL đang dùng rồi tự tìm lại qua mDNS. Profile `simulation` vẫn sử dụng
`host.wokwi.internal` và không phụ thuộc mDNS.

### 2.2. Thiết lập một lần trên mỗi máy Windows

Mở **PowerShell bằng Run as administrator**, sau đó chạy từng lệnh:

```powershell
Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private

New-NetFirewallRule -DisplayName "Mini Flood Backend TCP 8000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -RemoteAddress LocalSubnet -Profile Private

New-NetFirewallRule -DisplayName "Mini Flood mDNS UDP 5353" -Direction Inbound -Action Allow -Protocol UDP -LocalPort 5353 -RemoteAddress LocalSubnet -Profile Private
```

Hai firewall rule chỉ nhận kết nối từ mạng nội bộ (`LocalSubnet`):

- TCP 8000: ESP32 gửi telemetry tới FastAPI.
- UDP 5353: ESP32 tìm `mini-flood-backend.local` bằng mDNS.

Kiểm tra cấu hình:

```powershell
Get-NetConnectionProfile -InterfaceAlias "Wi-Fi"
Get-NetFirewallRule -DisplayName "Mini Flood*"
```

Kết quả cần có:

```text
NetworkCategory : Private
Mini Flood Backend TCP 8000 : Enabled
Mini Flood mDNS UDP 5353    : Enabled
```

Nếu máy không đặt tên card mạng là `Wi-Fi`, tìm đúng tên bằng:

```powershell
Get-NetAdapter
```

Sau đó thay `"Wi-Fi"` trong lệnh bằng giá trị ở cột `Name`.

### 2.3. Khởi động và kiểm tra backend

Chạy backend từ thư mục project và giữ Terminal mở:

```powershell
cd D:\Projects\tool-craw
python -m uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
```

Không dùng `--host 127.0.0.1`, vì địa chỉ đó chỉ cho chính laptop truy cập.

Kiểm tra trên laptop:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v2/health
```

API phải trả `status: ok`. Sau khi nạp profile `real_hardware`, Serial Monitor
phải xuất hiện:

```text
[BOOT] Backend discovery: mini-flood-backend.local:8000
[mDNS] Dang tim dich vu _mini-flood._tcp.local
[mDNS] Backend: mini-flood-backend.local -> http://192.168.1.xxx:8000/api/v2/telemetry
[HTTP] Phan hoi 200
```

Trang health trên ESP32 (`http://<IP-ESP32>/health`) phải có:

```json
{
  "backend": {
    "connected": true,
    "last_http_status": 200,
    "discovery": "mdns",
    "host": "mini-flood-backend.local"
  }
}
```

### 2.4. Cài project trên máy khác

1. Sao chép hoặc clone project.
2. Tạo môi trường Python và chạy `pip install -r requirements.txt`.
3. Tạo `.env` và `EPS32_PROJECT/include/secrets.h` từ file mẫu; dùng cùng
   `MINI_FLOOD_DEVICE_KEY` ở cả backend và ESP32.
4. Chạy các lệnh mạng ở mục 2.2 một lần với quyền Administrator.
5. Khởi động FastAPI bằng `--host 0.0.0.0 --port 8000`.
6. Không cần sửa IP hoặc nạp lại ESP32 chỉ vì chuyển backend sang máy mới;
   ESP32 sẽ tìm máy mới qua mDNS.

### 2.5. Xử lý sự cố mạng

| Hiện tượng | Kiểm tra |
|---|---|
| `connection refused` | Backend chưa chạy hoặc không bind `0.0.0.0:8000`. |
| ESP32 báo chưa tìm thấy mDNS | Kiểm tra mạng `Private`, UDP 5353 và cả hai thiết bị cùng Wi-Fi/LAN. |
| HTTP `401` | `MINI_FLOOD_DEVICE_KEY` của firmware và backend không giống nhau. |
| HTTP `200` nhưng dashboard không đổi | Kiểm tra `device_id`, API dashboard và SSE. |
| Laptop đổi IP | Không sửa firmware; giữ backend chạy và chờ ESP32 tìm mDNS lại. |
| Router bật AP/client isolation | Tắt isolation hoặc dùng backend cloud/tunnel. |

## 3. Cấu hình trạm

Dashboard có form cập nhật cấu hình. Có thể dùng API trực tiếp:

```powershell
$headers = @{ "X-Device-Key" = $env:MINI_FLOOD_DEVICE_KEY }
$config = @{
  overflow_level_cm = 40
  warning_margin_cm = 10
  hysteresis_cm = 2
  recovery_hold_seconds = 120
} | ConvertTo-Json

Invoke-RestMethod -Method Put `
  -Uri http://localhost:8000/api/v2/stations/mini-flood-station-01/config `
  -Headers $headers -ContentType "application/json" -Body $config
```

Thay đổi có hiệu lực từ telemetry kế tiếp và không yêu cầu huấn luyện lại model.

## 4. Thu thập và huấn luyện

Gọi `/api/v2/experiments/start`, chạy từng kịch bản độc lập, rồi xuất CSV:

```powershell
Invoke-WebRequest `
  "http://localhost:8000/api/v2/experiments/export.csv?device_id=mini-flood-station-01" `
  -Headers $headers -OutFile telemetry_experiments.csv

python train_mini_flood_models.py --input telemetry_experiments.csv --output-dir models
```

Artifacts:

- `mini_flood_15m.joblib`, `mini_flood_30m.joblib` nếu learned model thắng baseline.
- `mini_flood_metadata.json`.
- `mini_flood_benchmark.csv` với MAE/RMSE/R².
- `mini_flood_regression_validation.png`.

Khởi động lại API sau khi huấn luyện để nạp model mới.

## 5. Xác minh

```powershell
pytest -q
python simulate_iot_stream.py --scenario flow --speedup 0
pio run --project-dir EPS32_PROJECT -e simulation
pio run --project-dir EPS32_PROJECT -e real_hardware
```

Dashboard phải hiển thị số cm dự báo, trạng thái tổng hợp, hai đường ngưỡng và form cấu hình động. Telegram/email phải chứa dự báo 15/30 phút và mức tràn.
