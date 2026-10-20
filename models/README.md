# Model artifacts của V1

Thư mục này chứa model sinh ra bởi:

```powershell
python train_mini_flood_models.py --input telemetry_experiments.csv --output-dir models
```

Khi chưa có file model được huấn luyện, backend tự động sử dụng bộ dự báo quy tắc ngưỡng `mini-flood-baseline-v1`.
