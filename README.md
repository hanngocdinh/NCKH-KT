# Mini Flood AI — Runtime

Bản chạy gồm **model đã train, BE nhận telemetry và dashboard**. Không cần chạy training hoặc sinh dữ liệu để khởi động.

```text
IoT / HTTP → BE kiểm tra dữ liệu → tạo 4 feature → model đã train
→ forecast → cảnh báo → dashboard / Telegram
```

## Thành phần chính

| Thành phần | Vị trí |
|---|---|
| FastAPI nhận dữ liệu | mini_flood_api.py |
| Dashboard | app_mini_flood_dashboard.py |
| Xử lý dữ liệu, inference, DB, cảnh báo | mini_flood/ |
| Model đang dùng | models/current/ |
| Cấu hình inference 5 giây | config/ai.demo.json |
| Cấu hình thông báo | config/notifications.json |

Bundle hiện tại có ba Random Forest dự báo **15/30/60 giây**, train từ dữ liệu synthetic. Cần mode demo để nạp; không đổi nhãn thành model đã nghiệm thu thực tế. Model thiếu/hỏng/sai schema/hash trả forecast null; không fallback.

## Chạy

Dùng Python >=3.11. Phiên bản thư viện giải tuần tự model được pin trong requirements.txt.

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

Trong terminal khác, đặt cùng các biến môi trường rồi chạy:

```powershell
streamlit run app_mini_flood_dashboard.py
```

Xem [phân tích cập nhật IoT V3](docs/PHAN_TICH_CAP_NHAT_IOT_V3.md),
[hướng dẫn nhận dữ liệu, test HTTP và dashboard](docs/RUNTIME_GUIDE.md),
[API](docs/MINI_FLOOD_HTTP_GUIDE.md), [.env mẫu](.env.demo.example).

## Dữ liệu model cần

- IoT gửi mưa hiện tại, lượng mưa trong khoảng đo, nước hiện tại, timestamp và trạng thái cảm biến.
- BE tính tổng mưa 15 giây và độ dâng nước 10 giây; cần khoảng bốn mẫu hợp lệ tại giây 0/5/10/15.
- Mỗi mẫu mới hợp lệ sau warmup tạo một dự báo mới. Không training trong request.
- Demo dùng ngưỡng warning 30 cm, tràn 40 cm khi cấu hình trạm theo hướng dẫn; ngưỡng thật phải hiệu chuẩn riêng.
- Giữ ACK v1/v2, migration SQLite, timestamp UTC, chống trùng và snapshot tách live/history.

Mode real mặc định từ chối model synthetic. config/ai.json là profile 60 giây được giữ cho tương thích cấu hình, không khớp bundle 5 giây đang đóng gói; chọn config/ai.demo.json khi chạy model hiện tại.

## Kiểm thử runtime

```powershell
python -m pip install -r requirements-dev.txt
pytest -q
```

Training, generator, evaluation, dataset và model thử nghiệm cũ đã chuyển khỏi mã chính vào archive/ai_training (bản lưu local, không được runtime import). Trọng số models/current được giữ nguyên hash. Firmware IoT hiện là V3, gửi schema v2 mỗi 10 giây; cadence này chưa khớp profile model demo 5 giây.
