# Hướng dẫn HTTP Mini Flood V2

## Telemetry

ESP32 gửi `POST /api/v2/telemetry` với header `X-Device-Key`:

```json
{
  "schema_version": 1,
  "device_id": "mini-flood-station-01",
  "boot_id": "a1b2c3d4-e5f60718",
  "sequence_no": 1,
  "timestamp": "2026-10-20T10:00:00+07:00",
  "rain_interval_mm": 0.5,
  "rain_rate_mmh": 30.0,
  "water_level_cm": 12.5,
  "quality_flags": []
}
```

`water_level_cm` là mực nước tính từ đáy. ESP32 chỉ đo và gửi dữ liệu; nó không tự gán An toàn/Cảnh báo/Nguy hiểm.

## Cấu hình ngưỡng động

```powershell
$headers = @{ "X-Device-Key" = $env:MINI_FLOOD_DEVICE_KEY }
Invoke-RestMethod `
  http://localhost:8000/api/v2/stations/mini-flood-station-01/config `
  -Headers $headers
```

Cập nhật:

```powershell
$body = @{
  overflow_level_cm = 40
  warning_margin_cm = 10
  hysteresis_cm = 2
  recovery_hold_seconds = 120
} | ConvertTo-Json

Invoke-RestMethod -Method Put `
  http://localhost:8000/api/v2/stations/mini-flood-station-01/config `
  -Headers $headers -ContentType "application/json" -Body $body
```

Backend tính `warning_level_cm = overflow_level_cm - warning_margin_cm`. Cấu hình thay đổi có hiệu lực ở telemetry kế tiếp và không làm thay đổi forecast AI.

## Kết quả

`GET /api/v2/stations/{device_id}/latest` và history/SSE trả về các trường chính:

```json
{
  "water_level_cm": 25.0,
  "forecast_15m_cm": 31.4,
  "forecast_30m_cm": 36.8,
  "alert_level": 1,
  "alert_label": "Cảnh báo",
  "warning_level_cm": 30.0,
  "overflow_level_cm": 40.0,
  "model_version": "mini-flood-v2-...",
  "safety_override": false
}
```

`alert_level` là kết quả của quy tắc theo cấu hình trạm, không phải đầu ra của model.

## Các endpoint khác

- `GET /api/v2/health`
- `GET /api/v2/stations/{device_id}/history`
- `GET /api/v2/stream/sse`
- `WS /api/v2/stream/ws`
- `POST /api/v2/experiments/start`
- `POST /api/v2/experiments/stop`
- `GET /api/v2/experiments/export.csv`
- `POST /api/v2/notifications/test`
