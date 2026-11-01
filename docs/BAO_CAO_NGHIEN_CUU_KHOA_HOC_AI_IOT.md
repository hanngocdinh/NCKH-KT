# BÁO CÁO NGHIÊN CỨU KHOA HỌC KỸ THUẬT

# Hệ thống AI–IoT dự báo sớm mực nước trên mô hình thoát nước trường học

## 1. Phạm vi nghiên cứu

Đề tài là mô hình thử nghiệm kiểm chứng nguyên lý trên sa bàn, không phải hệ thống dự báo ngập cho toàn đô thị. Hệ thống kết hợp ESP32, cảm biến mưa, cảm biến mực nước, backend FastAPI, mô hình hồi quy, dashboard và thông báo Telegram/email.

Mục tiêu kỹ thuật:

- Đo mực nước và cường độ mưa theo chu kỳ.
- Dự báo mực nước sau các horizon trong cấu hình (mặc định 5/10/15 phút), chỉ dùng learned model.
- Tách kết quả AI khỏi ngưỡng cảnh báo của từng vị trí lắp đặt.
- Cảnh báo sớm trước khi nước chạm mức tràn của sa bàn.

## 2. Thu thập và xử lý dữ liệu

ESP32 gửi các trường `rain_interval_mm`, `rain_rate_mmh` và `water_level_cm` tới API `/api/v2/telemetry`. `water_level_cm` được tính từ đáy bể; khoảng cách lắp cảm biến chỉ phục vụ phép quy đổi tại firmware.

Backend tạo bốn đặc trưng tương thích chu kỳ IoT 60 giây:

| Đặc trưng | Ý nghĩa |
|---|---|
| `rain_rate_mmh` | Cường độ mưa hiện tại |
| `rain_sum_5m` | Tổng lượng mưa trong 5 phút |
| `water_level_cm` | Mực nước hiện tại |
| `water_rise_2m_cm` | Mức thay đổi mực nước trong 2 phút |

Dữ liệu được tách train/test theo lần thí nghiệm và thứ tự thời gian để tránh rò rỉ thông tin tương lai.

## 3. Mô hình dự báo

Đầu ra học máy là mực nước liên tục theo từng horizon; model thiếu/lỗi trả null:

\[
\hat{H}_{5},\quad \hat{H}_{10},\quad \hat{H}_{15}\quad (cm)
\]

Với mỗi horizon, hệ thống so sánh:

1. Persistence và chiếu tuyến tính chỉ dùng làm mốc so sánh offline.
2. Ridge Regression có chuẩn hóa đặc trưng.
3. Random Forest Regressor nông với độ sâu tối đa 4.

Các mô hình được đánh giá bằng MAE, RMSE và R². Tham số nghiệm thu đọc từ config/ai.json; chỉ dữ liệu thật mới được xét promote. Synthetic chỉ kiểm tra pipeline. P90/OOD/Gradient Boosting và water-only model tạm hoãn để giữ đơn giản.

## 4. Ngưỡng động theo vị trí

AI không trực tiếp dự đoán nhãn An toàn/Cảnh báo/Nguy hiểm. Mỗi trạm lưu:

- `overflow_level_cm`: mực nước bắt đầu tràn.
- `warning_margin_cm`: khoảng cảnh báo sớm trước mức tràn.
- `hysteresis_cm`: khoảng lùi chống dao động trạng thái.
- `recovery_hold_seconds`: thời gian ổn định trước khi hạ mức.

Ngưỡng cảnh báo được tính bằng:

\[
H_{warning}=H_{overflow}-warning\_margin
\]

Forecast từ model quyết định cảnh báo sớm. Quy tắc sensor_rule riêng nâng nguy hiểm khi nước thực tế mới, hợp lệ vượt mức tràn. Hysteresis được giữ; thiếu model không tự hạ mức hoặc kết luận An toàn. Mỗi quyết định có trace dữ liệu, config và model để debug.

Cấu hình mặc định của sa bàn là mức tràn 40 cm, vùng đệm 10 cm, hysteresis 2 cm và thời gian ổn định 120 giây. Các giá trị này được chỉnh trực tiếp trên dashboard mà không phải sửa mã nguồn hoặc huấn luyện lại AI.

## 5. Kiến trúc hệ thống

```text
Cảm biến → ESP32 → HTTP API V2 → SQLite
                              ├→ Feature engine → Regression forecast
                              ├→ Dynamic threshold + hysteresis
                              ├→ Dashboard/SSE
                              └→ Telegram và email
```

ESP32 có bộ đệm khi mất Wi-Fi và đánh số thứ tự gói tin để backend chống trùng lặp. Dữ liệu lỗi hoặc timestamp không hợp lệ được lưu để kiểm tra nhưng không dùng cho dự báo thông thường.

## 6. Kiểm chứng

Pipeline được kiểm thử ở các mức:

- Unit test cho feature, target tương lai, model registry và ngưỡng động.
- Integration test cho API, SQLite, SSE và hàng đợi thông báo.
- End-to-end test cho các kịch bản an toàn, cảnh báo, nguy hiểm, mất mạng và hồi phục.
- Build firmware bằng PlatformIO.

Kết quả nghiệm thu phải được lấy từ lần chạy `pytest` và PlatformIO gần nhất; không dùng số kiểm thử tĩnh trong báo cáo. Model chỉ được công bố sau khi metadata ghi `promoted=true`.

## 7. Giới hạn và hướng phát triển

- Dữ liệu hiện tại chủ yếu từ sa bàn và chưa đại diện cho điều kiện thủy văn ngoài thực địa.
- Cần bổ sung nhiều lần thí nghiệm độc lập với tốc độ mưa, dâng và rút khác nhau.
- Cần hiệu chuẩn cảm biến, bảo vệ nguồn điện và kiểm tra vùng mù siêu âm trước khi lắp ngoài trời.
- Không dùng kết quả prototype để ra quyết định an toàn thực tế khi chưa kiểm định thiết bị và dữ liệu hiện trường.
