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

## 2. Cấu hình trạm

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

## 3. Thu thập và huấn luyện

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

## 4. Xác minh

```powershell
pytest -q
python simulate_iot_stream.py --scenario flow --speedup 0
pio run --project-dir EPS32_PROJECT
```

Dashboard phải hiển thị số cm dự báo, trạng thái tổng hợp, hai đường ngưỡng và form cấu hình động. Telegram/email phải chứa dự báo 15/30 phút và mức tràn.
