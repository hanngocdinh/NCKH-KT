# Mini Flood AI V2

Prototype AI–IoT dự báo **mực nước sau 15 và 30 phút** từ dữ liệu cảm biến mưa và mực nước.

> **MÔ PHỎNG THỬ NGHIỆM:** kết quả dùng để kiểm chứng nguyên lý trên mô hình vật lý thu nhỏ, không phải hệ thống cảnh báo vận hành cho Hội An.

## Thiết kế V2

- ESP32 đo và gửi telemetry tới FastAPI qua HTTP.
- Ridge Regression và Random Forest nông được so sánh với baseline chiếu tuyến tính; model có MAE tốt nhất được chọn riêng cho từng horizon.
- AI chỉ dự báo `forecast_15m_cm` và `forecast_30m_cm`.
- Backend suy ra trạng thái An toàn/Cảnh báo/Nguy hiểm từ cấu hình động của từng `device_id`.
- Dashboard cho phép chỉnh mức tràn, vùng đệm cảnh báo, hysteresis và thời gian ổn định khi hạ mức.
- SQLite lưu telemetry, forecast, cấu hình trạm và hàng đợi Telegram/email.

## Bốn đặc trưng AI

| Đặc trưng | Ý nghĩa |
|---|---|
| `rain_rate_mmh` | Cường độ mưa hiện tại |
| `rain_sum_5m` | Mưa tích lũy 5 phút |
| `water_level_cm` | Mực nước hiện tại tính từ đáy |
| `water_rise_2m_cm` | Mức thay đổi của nước trong 2 phút |

## Ngưỡng động

Trạm demo `mini-flood-station-01` được seed với:

- Mức tràn: 40 cm.
- Vùng đệm: 10 cm, nên ngưỡng cảnh báo là 30 cm.
- Hysteresis: 2 cm.
- Thời gian ổn định trước khi hạ mức: 120 giây.

`SENSOR_MOUNT_HEIGHT_CM` trong firmware là khoảng cách từ đầu dò đến đáy để quy đổi phép đo. Nó không phải mức tràn. `overflow_level_cm` nằm trong cấu hình backend và có thể đổi trên dashboard mà không huấn luyện lại AI.

## Khởi chạy

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

$env:MINI_FLOOD_DEVICE_KEY = "replace-with-a-long-random-key"
python -m uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
```

Terminal khác:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run app_mini_flood_dashboard.py
```

- Health: `http://localhost:8000/api/v2/health`
- Swagger: `http://localhost:8000/docs`
- Dashboard: `http://localhost:8501`

## Huấn luyện và kiểm thử

```powershell
python train_mini_flood_models.py --input telemetry_experiments.csv --output-dir models
pytest -q
```

Model chưa đạt MAE tốt hơn baseline sẽ không được sử dụng. Xem [RUNBOOK.md](RUNBOOK.md) và [hướng dẫn HTTP V2](docs/MINI_FLOOD_HTTP_GUIDE.md) để vận hành hệ thống.

Xem [kiến trúc hệ thống](docs/ARCHITECTURE.md) để hiểu luồng ESP32, API, dự báo, ngưỡng động, chống trùng bằng `boot_id` và kênh cảnh báo.
