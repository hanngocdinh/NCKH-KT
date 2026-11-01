# Runbook — AI runtime

1. Cài requirements.txt bằng Python >=3.11.
2. Đặt mode/config/model/key/DB theo README hoặc .env.demo.example.
3. Chạy BE và xác nhận health model_ready=true.
4. Chạy dashboard với cùng key/device/API URL.
5. Cấu hình trạm rồi gửi telemetry từ IoT hoặc HTTP.

Chi tiết và lệnh: [RUNTIME_GUIDE.md](docs/RUNTIME_GUIDE.md).

Runtime không có lệnh training hoặc simulator. Bundle được nạp từ models/current.
Model lỗi không có dự báo thay thế. Code training và kết quả trước đây được lưu local ở archive/ai_training.

Phần cứng chưa sửa trong đợt này. Tài liệu IoT được giữ tại [EPS32_PROJECT/README.md](EPS32_PROJECT/README.md).
