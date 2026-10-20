# BÁO CÁO NGHIÊN CỨU KHOA HỌC KỸ THUẬT

# Hệ thống AI–IoT dự báo sớm mực nước trên mô hình thoát nước trường học

## 1. Phạm vi nghiên cứu

Đề tài là mô hình thử nghiệm kiểm chứng nguyên lý trên sa bàn, không phải hệ thống dự báo ngập cho toàn đô thị. Hệ thống kết hợp ESP32, cảm biến mưa, cảm biến mực nước, backend FastAPI, mô hình hồi quy, dashboard và thông báo Telegram/email.

Mục tiêu kỹ thuật:

- Đo mực nước và cường độ mưa theo chu kỳ.
- Dự báo mực nước sau 15 và 30 phút theo đơn vị centimet.
- Tách kết quả AI khỏi ngưỡng cảnh báo của từng vị trí lắp đặt.
- Cảnh báo sớm trước khi nước chạm mức tràn của sa bàn.

## 2. Thu thập và xử lý dữ liệu

ESP32 gửi các trường `rain_interval_mm`, `rain_rate_mmh` và `water_level_cm` tới API `/api/v2/telemetry`. `water_level_cm` được tính từ đáy bể; khoảng cách lắp cảm biến chỉ phục vụ phép quy đổi tại firmware.

Backend tạo bốn đặc trưng:

| Đặc trưng | Ý nghĩa |
|---|---|
| `rain_rate_mmh` | Cường độ mưa hiện tại |
| `rain_sum_5m` | Tổng lượng mưa trong 5 phút |
| `water_level_cm` | Mực nước hiện tại |
| `water_rise_2m_cm` | Mức thay đổi mực nước trong 2 phút |

Dữ liệu được tách train/test theo lần thí nghiệm và thứ tự thời gian để tránh rò rỉ thông tin tương lai.

## 3. Mô hình dự báo

Đầu ra học máy là hai giá trị liên tục:

\[
\hat{H}_{15},\quad \hat{H}_{30}\quad (cm)
\]

Với mỗi horizon, hệ thống so sánh:

1. Baseline chiếu tuyến tính từ tốc độ dâng gần nhất.
2. Ridge Regression có chuẩn hóa đặc trưng.
3. Random Forest Regressor nông với độ sâu tối đa 4.

Các mô hình được đánh giá bằng MAE, RMSE và R². Learned model chỉ được chọn khi MAE thấp hơn baseline trên tập kiểm thử độc lập.

Kết quả trên bộ dữ liệu synthetic hiện tại:

| Horizon | Model được chọn | MAE model | MAE baseline |
|---|---:|---:|---:|
| 15 phút | Ridge | 0,562 cm | 1,453 cm |
| 30 phút | Random Forest | 0,906 cm | 2,757 cm |

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

Backend so sánh giá trị lớn nhất trong mực nước hiện tại, dự báo 15 phút và dự báo 30 phút với hai ngưỡng. Trạng thái tăng ngay khi vượt ngưỡng nhưng chỉ hạ từng mức sau khi nằm dưới ngưỡng trừ hysteresis đủ thời gian quy định.

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

Kết quả nghiệm thu hiện tại: 27 kiểm thử Python thành công, firmware ESP32 build thành công và luồng simulator tới API V2 hoạt động đầy đủ.

## 7. Giới hạn và hướng phát triển

- Dữ liệu hiện tại chủ yếu từ sa bàn và chưa đại diện cho điều kiện thủy văn ngoài thực địa.
- Cần bổ sung nhiều lần thí nghiệm độc lập với tốc độ mưa, dâng và rút khác nhau.
- Cần hiệu chuẩn cảm biến, bảo vệ nguồn điện và kiểm tra vùng mù siêu âm trước khi lắp ngoài trời.
- Không dùng kết quả prototype để ra quyết định an toàn thực tế khi chưa kiểm định thiết bị và dữ liệu hiện trường.
