"""Gửi telemetry IoT giả lập để tìm điểm chuyển Level cảnh báo.

Ví dụ:
    python simulate_iot_alert_thresholds.py --device-key change-this-demo-key

Script dùng HTTP contract thật của backend. Nó không train model, không sửa model
và không giả lập kết quả forecast ở phía client.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

import requests

from mini_flood.notifications import format_horizon

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def build_water_levels(
    start: float,
    end: float,
    step: float,
    warmup_samples: int,
) -> list[float]:
    if not all(math.isfinite(value) for value in (start, end, step)):
        raise ValueError("Mực nước và bước tăng phải là số hữu hạn")
    if start < 0 or end < start or step <= 0:
        raise ValueError("Cần 0 <= start <= end và step > 0")
    if warmup_samples < 1:
        raise ValueError("warmup_samples phải >= 1")
    levels = [start] * warmup_samples
    value = start + step
    while value <= end + 1e-9:
        levels.append(round(value, 6))
        value += step
    return levels


def build_payload(
    *,
    device_id: str,
    boot_id: str,
    sequence_no: int,
    timestamp: datetime,
    interval_seconds: float,
    rain_rate_mmh: float,
    water_level_cm: float,
) -> dict[str, Any]:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("timestamp phải có timezone")
    return {
        "schema_version": 2,
        "device_id": device_id,
        "boot_id": boot_id,
        "sequence_no": sequence_no,
        "timestamp": timestamp.astimezone(timezone.utc).isoformat(),
        "sample_interval_ms": int(round(interval_seconds * 1000)),
        "sample_age_ms": 0,
        "rain_interval_mm": round(rain_rate_mmh * interval_seconds / 3600, 6),
        "rain_rate_mmh": rain_rate_mmh,
        "water_level_cm": water_level_cm,
        "quality_flags": [],
    }


def extract_observation(event: dict[str, Any]) -> dict[str, Any]:
    inference = event.get("inference") or {}
    ready: list[tuple[int, float]] = []
    for item in inference.get("forecasts") or []:
        if item.get("status") != "ready" or item.get("level_cm") is None:
            continue
        try:
            horizon = int(item["horizon_seconds"])
            level = float(item["level_cm"])
        except (KeyError, TypeError, ValueError):
            continue
        if horizon > 0 and math.isfinite(level):
            ready.append((horizon, level))
    ready.sort()
    controlling = max(ready, key=lambda pair: pair[1]) if ready else None
    return {
        "water_level_cm": event.get("water_level_cm"),
        "rain_rate_mmh": event.get("rain_rate_mmh"),
        "rain_interval_mm": event.get("rain_interval_mm"),
        "quality_status": event.get("quality_status"),
        "inference_status": inference.get("status"),
        "forecasts": ready,
        "controlling_horizon": controlling[0] if controlling else None,
        "max_forecast_cm": controlling[1] if controlling else None,
        "alert_level": event.get("alert_level"),
        "alert_label": event.get("alert_label"),
        "alert_source": event.get("alert_source"),
        "main_factor": event.get("main_factor"),
    }


def format_observation(sequence_no: int, observation: dict[str, Any]) -> str:
    forecasts = observation["forecasts"]
    forecast_text = " | ".join(
        f"+{format_horizon(horizon)}={level:.1f}cm" for horizon, level in forecasts
    ) or "chưa có forecast"
    level = observation.get("alert_level")
    label = observation.get("alert_label") or "Chưa đánh giá"
    source = observation.get("alert_source") or "-"
    rain_rate = float(observation.get("rain_rate_mmh") or 0)
    return (
        f"seq={sequence_no:02d} | nước={float(observation['water_level_cm']):5.1f}cm | "
        f"mưa={rain_rate:6.1f}mm/h | "
        f"AI={observation.get('inference_status') or '-':<15} | {forecast_text} | "
        f"Level={level if level is not None else '-'} {label} | nguồn={source}"
    )


class MiniFloodApi:
    def __init__(self, api_base: str, device_key: str, timeout: float) -> None:
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"X-Device-Key": device_key})

    def _json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self.session.request(
            method,
            f"{self.api_base}{path}",
            timeout=self.timeout,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()

    def health(self) -> dict[str, Any]:
        return self._json("GET", "/health")

    def configure_station(
        self,
        device_id: str,
        *,
        overflow_level_cm: float,
        warning_margin_cm: float,
        hysteresis_cm: float,
        recovery_hold_seconds: int,
    ) -> dict[str, Any]:
        return self._json(
            "PUT",
            f"/stations/{device_id}/config",
            json={
                "overflow_level_cm": overflow_level_cm,
                "warning_margin_cm": warning_margin_cm,
                "hysteresis_cm": hysteresis_cm,
                "recovery_hold_seconds": recovery_hold_seconds,
            },
        )

    def send_telemetry(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._json("POST", "/telemetry", json=payload)

    def snapshot(self, device_id: str) -> dict[str, Any]:
        return self._json("GET", f"/stations/{device_id}/snapshot")


def run_sweep(args: argparse.Namespace) -> int:
    api = MiniFloodApi(args.api_base, args.device_key, args.timeout)
    health = api.health()
    if not health.get("model_ready"):
        print(f"LỖI: model chưa sẵn sàng: {health.get('model_errors')}", file=sys.stderr)
        return 2

    station = api.configure_station(
        args.device_id,
        overflow_level_cm=args.overflow,
        warning_margin_cm=args.warning_margin,
        hysteresis_cm=args.hysteresis,
        recovery_hold_seconds=args.recovery_hold,
    )
    warning_level = float(station["warning_level_cm"])
    levels = build_water_levels(
        args.start_water,
        args.end_water,
        args.water_step,
        args.warmup_samples,
    )
    estimated_seconds = max(0, len(levels) - 1) * args.interval_seconds
    boot_id = "threshold-" + uuid.uuid4().hex

    print("=" * 88)
    print("MÔ PHỎNG TÌM NGƯỠNG ALERT")
    print(f"API: {args.api_base}")
    print(f"Thiết bị QA: {args.device_id} | boot_id: {boot_id}")
    print(
        f"Ngưỡng cấu hình: warning={warning_level:.1f}cm, "
        f"overflow={args.overflow:.1f}cm, hysteresis={args.hysteresis:.1f}cm"
    )
    print(
        f"Model: {health.get('model_version')} | horizons={health.get('forecast_horizons_seconds')} | "
        f"nguồn={health.get('data_source')}"
    )
    print(
        f"Số mẫu={len(levels)}, nhịp={args.interval_seconds:g}s, "
        f"thời gian dự kiến≈{estimated_seconds:.0f}s"
    )
    print("=" * 88)

    first_warning: dict[str, Any] | None = None
    first_danger: dict[str, Any] | None = None

    for sequence_no, water_level in enumerate(levels):
        payload = build_payload(
            device_id=args.device_id,
            boot_id=boot_id,
            sequence_no=sequence_no,
            timestamp=datetime.now(timezone.utc),
            interval_seconds=args.interval_seconds,
            rain_rate_mmh=args.rain_rate,
            water_level_cm=water_level,
        )
        api.send_telemetry(payload)
        snapshot = api.snapshot(args.device_id)
        event = snapshot.get("current_inference") or snapshot.get("last_received") or {}
        observation = extract_observation(event)
        print(format_observation(sequence_no, observation), flush=True)

        record = {"sequence_no": sequence_no, **observation}
        alert_level = observation.get("alert_level")
        if first_warning is None and alert_level is not None and int(alert_level) == 1:
            first_warning = record
        if first_danger is None and alert_level is not None and int(alert_level) >= 2:
            first_danger = record
            if not args.continue_after_danger:
                break
        if sequence_no < len(levels) - 1:
            time.sleep(args.interval_seconds)

    print("\n" + "=" * 88)
    print("KẾT QUẢ")
    if first_warning:
        max_forecast = first_warning["max_forecast_cm"]
        max_forecast_text = "-" if max_forecast is None else f"{max_forecast:.1f}cm"
        horizon = first_warning["controlling_horizon"]
        horizon_text = "-" if horizon is None else f"{horizon}s"
        print(
            f"Level 1 xuất hiện lần đầu tại nước={first_warning['water_level_cm']:.1f}cm; "
            f"mưa={float(first_warning.get('rain_rate_mmh') or 0):.1f}mm/h; "
            f"max forecast={max_forecast_text}; "
            f"horizon={horizon_text}; "
            f"nguồn={first_warning['alert_source']}."
        )
    else:
        print("Chưa tìm thấy Level 1 trong khoảng đã quét.")
    if first_danger:
        print(
            f"Level 2 xuất hiện lần đầu tại nước={first_danger['water_level_cm']:.1f}cm; "
            f"mưa={float(first_danger.get('rain_rate_mmh') or 0):.1f}mm/h; "
            f"nguồn={first_danger['alert_source']}."
        )
    else:
        print("Chưa tìm thấy Level 2 trong khoảng đã quét.")
    print(f"Xem dashboard với device ID: {args.device_id}")
    print("=" * 88)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gửi telemetry IoT schema v2 và tìm điểm chuyển Level cảnh báo",
    )
    parser.add_argument(
        "--api-base",
        default=os.getenv("MINI_FLOOD_API_BASE", "http://127.0.0.1:8000/api/v2"),
    )
    parser.add_argument("--device-key", default=os.getenv("MINI_FLOOD_DEVICE_KEY"))
    parser.add_argument(
        "--device-id",
        default=None,
        help="Mặc định tự tạo device QA mới để không dùng lại alert state của lần trước",
    )
    parser.add_argument("--interval-seconds", type=float, default=5.0)
    parser.add_argument("--warmup-samples", type=int, default=4)
    parser.add_argument("--start-water", type=float, default=10.0)
    parser.add_argument("--end-water", type=float, default=42.0)
    parser.add_argument("--water-step", type=float, default=2.0)
    parser.add_argument(
        "--rain-rate",
        type=float,
        default=0.0,
        help="Cường độ mưa cố định trong lần quét, đơn vị mm/h; mặc định 0",
    )
    parser.add_argument("--overflow", type=float, default=40.0)
    parser.add_argument("--warning-margin", type=float, default=10.0)
    parser.add_argument("--hysteresis", type=float, default=2.0)
    parser.add_argument("--recovery-hold", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--continue-after-danger", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not args.device_key:
        parser.error("Thiếu --device-key hoặc MINI_FLOOD_DEVICE_KEY trong .env")
    if not args.device_id:
        args.device_id = "qa-threshold-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    if args.interval_seconds <= 0 or args.timeout <= 0:
        parser.error("interval-seconds và timeout phải > 0")
    if args.rain_rate < 0:
        parser.error("rain-rate phải >= 0")
    try:
        return run_sweep(args)
    except KeyboardInterrupt:
        print("\nĐã dừng mô phỏng bằng Ctrl+C. Các mẫu đã gửi vẫn được giữ trong backend.")
        return 130
    except requests.RequestException as exc:
        print(f"LỖI HTTP: {exc}", file=sys.stderr)
        return 3
    except (KeyError, TypeError, ValueError) as exc:
        print(f"LỖI DỮ LIỆU: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
