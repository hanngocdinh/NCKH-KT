# Mini Flood AI

Prototype AI–IoT dự báo nguy cơ ngập cục bộ trước 15 và 30 phút từ dữ liệu cảm biến mưa và mực nước.

> **MÔ PHỎNG THỬ NGHIỆM:** kết quả chỉ dùng để kiểm chứng nguyên lý trên mô hình vật lý thu nhỏ, không phải dự báo vận hành cho Hội An.

## Phạm vi V1

- ESP32 chỉ đo và gửi telemetry qua HTTP.
- Backend FastAPI kiểm tra, lưu SQLite và tạo đặc trưng.
- Hai model Multinomial Logistic Regression dự báo cho 15 và 30 phút.
- Quy tắc ngưỡng trên backend đóng vai trò baseline và lớp bảo vệ.
- Dashboard, Telegram và email cung cấp thông tin cho người dùng.
- Không có lệnh điều khiển, đèn hoặc còi phản hồi từ backend về ESP32.

## Bốn đặc trưng AI

| Đặc trưng | Ý nghĩa |
|---|---|
| `rain_rate_mmh` | Cường độ mưa hiện tại |
| `rain_sum_5m` | Mưa tích lũy 5 phút |
| `water_level_cm` | Mực nước hiện tại |
| `water_rise_2m_cm` | Tốc độ dâng nước trong 2 phút |

## Cấu trúc repository

```text
mini_flood/                 Backend, feature engine, model và thông báo
mini_flood_api.py           Entry point FastAPI
app_mini_flood_dashboard.py Dashboard Streamlit
train_mini_flood_models.py  Huấn luyện Logistic Regression 15/30 phút
firmware/esp32_http/        Firmware ESP32 chỉ gửi telemetry
tests/                      Kiểm thử pipeline V1
docs/                       Proposal và hướng dẫn V1
models/                     Model V1 sinh ra sau khi huấn luyện
```

## Khởi chạy nhanh

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

- API health: `http://localhost:8000/api/v1/health`
- Swagger: `http://localhost:8000/docs`
- Dashboard: `http://localhost:8501`

## Huấn luyện

Sau khi thu thập ít nhất ba lần chạy cho mỗi kịch bản:

```powershell
python train_mini_flood_models.py --input telemetry_experiments.csv --output-dir models
```

Khởi động lại API sau khi train để nạp model mới. Nếu model chưa đạt tiêu chí hoặc chưa tồn tại, backend dùng baseline theo ngưỡng.

## Kiểm thử

```powershell
pytest -q
```

Xem [RUNBOOK.md](RUNBOOK.md) để biết quy trình vận hành, [Kế hoạch thu thập dữ liệu thật & Cảnh báo Telegram](docs/KE_HOACH_TRAIN_DU_LIEU_THAT_VA_CANH_BAO_TELEGRAM.md), [Hướng dẫn kiểm thử thủ công Wokwi & IoT](docs/HUONG_DAN_TEST_THU_CONG_WOKWI_IOT.md), và [Proposal V1](docs/DE_XUAT_AI_IOT_DU_BAO_NGAP_V1.md) để biết phạm vi nghiên cứu.

