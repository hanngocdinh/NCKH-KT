# Runtime hiện tại và IoT backlog

## Đã giữ

- Model đã train ở models/current, ba horizon 15/30/60 giây, nguyên SHA256.
- Source BE nhận IoT, feature engine, inference, DB, cảnh báo và dashboard.
- Cấu hình chỉ phục vụ inference/notification; không còn CV/hyperparameter trong runtime.
- Payload v1/v2 và lịch sử DB vẫn được hỗ trợ.

## Đã tách khỏi mã chính

Training, sinh dữ liệu, simulator, evaluation, test training và tài liệu training được
lưu local tại archive/ai_training. Dataset/model cũ giữ tại đó; runtime không import.
Xem [RUNTIME_GUIDE.md](RUNTIME_GUIDE.md) để chạy BE/dashboard và gửi HTTP thủ công.

## IoT đã cập nhật trong source, còn cần nghiệm thu

Firmware source hiện là V3, gửi schema v2 mỗi 10 giây và có metadata interval/age.
Backend đã xử lý timestamp, boot, duplicate, buffer cũ, snapshot và sensor health.

Các việc còn lại:

1. Xác minh cadence thật trước khi dùng model kỳ vọng 5 giây; firmware source 10 giây không chứng minh nhịp thiết bị đang flash.
2. Đối chiếu siêu âm/analog và nguồn water_level_cm.
3. Hiệu chuẩn mốc đo, chiều cao/vùng mù và điện áp Echo.
4. Kiểm tra frame/register/scale/counter mưa và rain_interval_mm.
5. Đánh giá buffer, tải cảm biến/mạng nếu đổi cadence.
6. Đo ngưỡng tràn/warning và nghiệm thu dữ liệu thật trước triển khai thực tế.

Xem [phân tích cập nhật IoT V3](PHAN_TICH_CAP_NHAT_IOT_V3.md) để biết contract,
rủi ro cadence và checklist nghiệm thu.
