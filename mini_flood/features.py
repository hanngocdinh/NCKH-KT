from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from .ai_settings import AIConfig, FEATURE_NAMES, load_ai_config

WATER_INVALID_FLAGS = {"water_sensor_invalid", "water_sensor_timeout", "water_not_calibrated"}
RAIN_INVALID_FLAGS = {"rain_sensor_unverified", "rain_sensor_invalid"}
TIME_INVALID_FLAGS = {"clock_invalid", "clock_reconstructed", "timestamp_in_future", "stale_timestamp", "out_of_order"}
KNOWN_FLAGS = WATER_INVALID_FLAGS | RAIN_INVALID_FLAGS | TIME_INVALID_FLAGS | {"unexpected_sample_interval"}


def _parse_time(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("measurement timestamp requires timezone")
    return parsed.astimezone(timezone.utc)


def _flags(row: dict[str, Any]) -> set[str]:
    value = row.get("quality_flags", [])
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {"quality_flags_invalid"}
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return {"quality_flags_invalid"}
    return set(value)


def sensor_validity(row: dict[str, Any]) -> tuple[bool, bool]:
    flags = _flags(row)
    unknown = bool(flags - KNOWN_FLAGS)
    return not (unknown or flags & WATER_INVALID_FLAGS), not (unknown or flags & RAIN_INVALID_FLAGS)


def build_features(rows: list[dict[str, Any]], config: AIConfig | None = None) -> tuple[dict[str, float] | None, str]:
    cfg = config or load_ai_config()
    if not rows:
        return None, "warming_up"
    try:
        ordered = sorted(rows, key=lambda row: (_parse_time(row["timestamp"]), int(row["sequence_no"])))
        current = ordered[-1]
        device = current.get("device_id")
        boot = current.get("boot_id", "legacy")
        end = _parse_time(current["timestamp"])
        window = max(cfg.data.rain_window_seconds, cfg.data.rise_window_seconds)
        start = end - timedelta(seconds=window)
        history = [
            row for row in ordered
            if row.get("device_id") == device and row.get("boot_id", "legacy") == boot
            and start - timedelta(seconds=cfg.data.lookup_tolerance_seconds) <= _parse_time(row["timestamp"]) <= end
        ]
        # Invalid points break the window; never filter them out and bridge the gap.
        for row in history:
            if not all(sensor_validity(row)) or _flags(row) & TIME_INVALID_FLAGS:
                return None, "invalid_input"
            if row.get("quality_status") in {"unknown", "invalid", "stale"}:
                return None, "invalid_input"
            if any(not math.isfinite(float(row[name])) or float(row[name]) < 0
                   for name in ("rain_rate_mmh", "rain_interval_mm", "water_level_cm")):
                return None, "invalid_input"
        if not history or _parse_time(history[0]["timestamp"]) > start:
            return None, "warming_up"
        times = [_parse_time(row["timestamp"]) for row in history]
        if any(not 0 < (right - left).total_seconds() <= cfg.data.max_gap_seconds
               for left, right in zip(times, times[1:])):
            return None, "warming_up"
        target = end - timedelta(seconds=cfg.data.rise_window_seconds)
        candidates = [row for row in history if _parse_time(row["timestamp"]) <= target]
        if not candidates:
            return None, "warming_up"
        reference = candidates[-1]
        if (target - _parse_time(reference["timestamp"])).total_seconds() > cfg.data.lookup_tolerance_seconds:
            return None, "warming_up"
        rain_start = end - timedelta(seconds=cfg.data.rain_window_seconds)
        rain_rows = [row for row in history if rain_start < _parse_time(row["timestamp"]) <= end]
        # An interval crossing the left boundary cannot be allocated without inventing rain.
        if rain_rows:
            first_rain = rain_rows[0]
            interval_ms = first_rain.get("sample_interval_ms")
            interval = (float(interval_ms) / 1000 if interval_ms is not None and math.isfinite(float(interval_ms)) and float(interval_ms) > 0 else
                        (_parse_time(first_rain["timestamp"]) - times[times.index(_parse_time(first_rain["timestamp"])) - 1]).total_seconds())
            if (_parse_time(first_rain["timestamp"]) - timedelta(seconds=interval) <
                    rain_start - timedelta(seconds=cfg.data.lookup_tolerance_seconds)):
                return None, "warming_up"
        features = {
            "rain_rate_mmh": float(current["rain_rate_mmh"]),
            "rain_sum_window_mm": sum(float(row["rain_interval_mm"]) for row in rain_rows),
            "water_level_cm": float(current["water_level_cm"]),
            "water_delta_window_cm": float(current["water_level_cm"]) - float(reference["water_level_cm"]),
        }
        return {name: round(features[name], cfg.output_decimals) for name in FEATURE_NAMES}, "ready"
    except (ValueError, TypeError, KeyError, OverflowError):
        return None, "invalid_input"


def identify_main_factor(features: dict[str, float], config: AIConfig | None = None) -> str:
    cfg = (config or load_ai_config()).explanation
    rain = features["rain_rate_mmh"] >= cfg.heavy_rain_rate_mmh or features["rain_sum_window_mm"] >= cfg.heavy_rain_sum_mm
    rise = features["water_delta_window_cm"] >= cfg.fast_rise_cm
    if rain and rise:
        return "Mưa lớn và nước đang dâng nhanh"
    if rise:
        return "Mực nước đang dâng nhanh"
    if rain:
        return "Cường độ mưa lớn"
    return "Mực nước và mưa đang ổn định"
