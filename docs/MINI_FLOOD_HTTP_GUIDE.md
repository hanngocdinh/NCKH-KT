# HTTP contract — Backend model-only

## Nhận dữ liệu

Giữ endpoint `POST /api/v2/telemetry` và header `X-Device-Key`. Firmware ESP32 V3
gửi payload schema v2:

```json
{
  "schema_version": 2,
  "device_id": "mini-flood-station-01",
  "boot_id": "boot-session",
  "sequence_no": 1,
  "timestamp": "2026-11-01T12:00:00+07:00",
  "sample_interval_ms": 10000,
  "sample_age_ms": 0,
  "rain_interval_mm": 0.5,
  "rain_rate_mmh": 30,
  "water_level_cm": 12.5,
  "quality_flags": []
}
```

ACK chỉ gồm `accepted`, `duplicate`, `quality_status` và `server_timestamp`.
Backend vẫn nhận schema v1 để tương thích client cũ. Schema v2 bắt buộc có
`sample_interval_ms`; `sample_age_ms` biểu diễn tuổi mẫu khi nằm trong buffer và
không được dùng để thay timestamp đo.

Backend giữ timestamp đo hợp lệ, chuẩn hóa UTC, lưu server_timestamp riêng.
Đồng hồ lỗi: timestamp lưu thay bằng giờ server, raw_payload giữ giờ gốc,
timestamp_source=server và clock_invalid. Gói đó không dùng cho model hoặc sensor_rule.
Gói quá cũ/sai thứ tự chỉ lưu lịch sử, không thay cảnh báo hiện tại.

## Kết quả và truy vết

GET /api/v2/stations/{device_id}/latest, history và SSE có inference:

```json
{
  "status": "ready",
  "mode": "model",
  "model_version": "mini-flood-model-...",
  "config_hash": "...",
  "forecasts": [
    {
      "horizon_seconds": 15,
      "horizon_minutes": null,
      "target_timestamp": "2026-10-31T10:00:15+00:00",
      "level_cm": 31.2,
      "upper_p90_cm": null,
      "algorithm": "ridge",
      "model_version": "mini-flood-model-...",
      "artifact_hash": "...",
      "status": "ready",
      "error": null
    }
  ]
}
```

Danh sách horizon đọc từ cấu hình. Các trạng thái: ready, warming_up, invalid_input,
model_unavailable, prediction_failed. Lỗi ở một horizon không làm mất forecast hợp lệ
của horizon khác; forecast lỗi là null. Chỉ được hạ cảnh báo khi có đầy đủ kết quả hợp lệ.
Forecast một phần vẫn được nâng cảnh báo nếu model hợp lệ phát hiện vượt ngưỡng.

alert_source=model cho cảnh báo theo forecast; sensor_rule chỉ dùng khi số đo nước
mới và hợp lệ vượt mức tràn. Chưa có cơ sở đánh giá thì alert_level/alert_label là null.
Khi mất model, giữ mức trước đó và hiển thị inference lỗi, không tự trả An toàn.

inference_trace trong latest/history chứa payload gốc, thời gian đo/nhận, feature vector,
config hash, model/version/hash, output, thời lượng xử lý, station config và quyết định.
forecast_15m_cm giữ tương thích; forecast_30m_cm=null với pipeline mới.
P90 trả null và không tham gia quyết định.

GET /api/v2/health cho biết cấu hình và lỗi load model.
PUT /api/v2/stations/{device_id}/config cập nhật ngưỡng, không xóa mức cảnh báo đang giữ.
Các API experiment/start, stop, export.csv, notification test và SSE/WebSocket giữ đường dẫn.


## Snapshot và chế độ demo

GET /api/v2/stations/{device_id}/snapshot (X-Device-Key) trả last_received,
current_measurement, current_inference, last_successful_inference và alert_state;
mỗi item có age_seconds/stale. Dashboard dùng snapshot để gói cũ không thay live.

Inference schema_version=2 có runtime_mode, data_source và demo_approved.
Horizon mới dùng giây; target_timestamp tính từ giờ đo. Health có
forecast_horizons_seconds, runtime_mode, data_source và model_demo_approved.
Mode real mặc định từ chối synthetic; mode demo chỉ nạp bundle synthetic qua gate.
Forecast 15 giây không được ghi vào forecast_15m_cm; field đó chỉ có giá trị cho
horizon 900 giây. Adapter lịch sử đổi phút cũ sang giây khi đọc.

POST /notifications/test chỉ enqueue; worker thực hiện gửi nếu được bật.
Xem [phân tích cập nhật IoT V3](PHAN_TICH_CAP_NHAT_IOT_V3.md) và
[hướng dẫn runtime](RUNTIME_GUIDE.md).
