# Model artifacts của V2

Thư mục này chứa model sinh ra bởi:

```powershell
python train_mini_flood_models.py --input telemetry_experiments.csv --output-dir models
```

Mỗi horizon so sánh Ridge Regression và Random Forest nông với baseline chiếu tuyến tính. Chỉ model có MAE thấp hơn baseline mới được lưu và nạp. Khi chưa có learned model phù hợp, backend dùng `mini-flood-regression-baseline-v2`.
