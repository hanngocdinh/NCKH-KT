# Kế hoạch thu thập dữ liệu, huấn luyện hồi quy và cảnh báo Telegram

## 1. Mục tiêu

Thu thập các lần thí nghiệm độc lập để huấn luyện model dự báo mực nước sau 15 và 30 phút, đánh giá bằng MAE/RMSE/R² và kiểm chứng cảnh báo theo ngưỡng động của sa bàn.

## 2. Chuẩn bị

- Chu kỳ gửi thực tế: 60 giây.
- Cấu hình trạm đã nhập đúng mức tràn, vùng đệm, hysteresis và thời gian hạ mức.
- Đồng hồ ESP32 đã đồng bộ SNTP.
- `MINI_FLOOD_DEVICE_KEY` của firmware trùng backend.
- Telegram token/chat ID chỉ lưu trong `.env`, không commit vào Git.

## 3. Kịch bản thí nghiệm

Mỗi lần chạy phải có `experiment_id` riêng và kéo dài hơn 30 phút:

| Kịch bản | Mưa | Diễn biến nước | Số lần tối thiểu |
|---|---|---|---:|
| Bình thường | Không/nhỏ | Ổn định thấp | 3 |
| Cảnh báo | Vừa/lớn | Dâng gần vùng đệm | 3 |
| Nguy hiểm | Lớn | Dâng tới mức tràn | 3 |
| Hồi phục | Giảm dần | Dâng rồi rút | 3 |

Không trộn nhiều kịch bản không liên quan vào cùng một `experiment_id`.

## 4. Thu thập qua API V2

```powershell
$headers = @{ "X-Device-Key" = $env:MINI_FLOOD_DEVICE_KEY }
$body = @{
  device_id = "mini-flood-station-01"
  experiment_id = "warning-run-01"
  scenario = "warning"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/v2/experiments/start `
  -Headers $headers -ContentType "application/json" -Body $body
```

Kết thúc và xuất dữ liệu:

```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/api/v2/experiments/stop?device_id=mini-flood-station-01" `
  -Headers $headers

Invoke-WebRequest `
  -Uri "http://localhost:8000/api/v2/experiments/export.csv?device_id=mini-flood-station-01" `
  -Headers $headers -OutFile telemetry_experiments.csv
```

## 5. Huấn luyện

```powershell
python train_mini_flood_models.py `
  --input telemetry_experiments.csv `
  --output-dir models
```

Pipeline tạo target tại đúng T+15/T+30, chia train/test theo experiment, huấn luyện Ridge và Random Forest nông, rồi so sánh với baseline chiếu tuyến tính. Learned model chỉ được chọn nếu MAE thấp hơn baseline.

Artifacts cần kiểm tra:

- `mini_flood_metadata.json`
- `mini_flood_benchmark.csv`
- `mini_flood_regression_validation.png`
- `mini_flood_15m.joblib` và `mini_flood_30m.joblib` khi learned model được chọn

## 6. Telegram và email

Thông báo phải chứa:

- Mực nước hiện tại.
- Forecast 15 và 30 phút theo cm.
- Trạng thái tổng hợp.
- Ngưỡng cảnh báo và mức tràn đang áp dụng.
- Yếu tố chính khiến nước dâng.

Kiểm tra kết nối:

```powershell
python test_telegram_ping.py
Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/api/v2/notifications/test?device_id=mini-flood-station-01" `
  -Headers $headers
```

## 7. Tiêu chí nghiệm thu

- Không có experiment bị dùng đồng thời cho train và test.
- Benchmark có đủ baseline, Ridge và Random Forest cho hai horizon.
- API latest/history không chứa xác suất phân loại.
- Đổi cấu hình trạm làm thay đổi trạng thái từ telemetry kế tiếp mà không đổi forecast AI.
- Cảnh báo tăng ngay; hạ từng mức sau khi thỏa hysteresis đủ thời gian.
- `pytest -q` và PlatformIO build thành công.
