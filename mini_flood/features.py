from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .config import FEATURE_NAMES


def _parse_time(value: str | datetime) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def _latest_at_or_before(rows: list[dict[str, Any]], target: datetime) -> dict[str, Any] | None:
    candidates = [row for row in rows if _parse_time(row["timestamp"]) <= target]
    return candidates[-1] if candidates else None


def _sum_window(rows: list[dict[str, Any]], end: datetime, minutes: int) -> float:
    start = end - timedelta(minutes=minutes)
    return float(
        sum(
            float(row["rain_interval_mm"])
            for row in rows
            if start < _parse_time(row["timestamp"]) <= end
        )
    )


def build_features(
    rows: list[dict[str, Any]],
    expected_interval_seconds: int = 60,
) -> tuple[dict[str, float] | None, str]:
    """Tạo feature chỉ từ dữ liệu tại hoặc trước bản ghi cuối cùng."""
    if not rows:
        return None, "warming_up"

    ordered = sorted(rows, key=lambda row: (_parse_time(row["timestamp"]), int(row["sequence_no"])))
    current = ordered[-1]
    end = _parse_time(current["timestamp"])
    start_15 = end - timedelta(minutes=15)
    history_15 = [row for row in ordered if start_15 <= _parse_time(row["timestamp"]) <= end]

    if not history_15 or _parse_time(history_15[0]["timestamp"]) > start_15 + timedelta(seconds=expected_interval_seconds * 1.5):
        return None, "warming_up"

    row_5m = _latest_at_or_before(ordered, end - timedelta(minutes=5))
    row_15m = _latest_at_or_before(ordered, end - timedelta(minutes=15))
    if row_5m is None or row_15m is None:
        return None, "warming_up"

    expected_points = max(1, int(15 * 60 / expected_interval_seconds) + 1)
    valid_points = sum(1 for row in history_15 if row.get("quality_status", "valid") == "valid")
    missing_ratio = max(0.0, min(1.0, 1.0 - valid_points / expected_points))

    current_level = float(current["water_level_cm"])
    features = {
        "rain_rate_mmh": float(current["rain_rate_mmh"]),
        "rain_sum_5m": _sum_window(ordered, end, 5),
        "rain_sum_15m": _sum_window(ordered, end, 15),
        "rain_sum_30m": _sum_window(ordered, end, 30),
        "water_level_cm": current_level,
        "water_rise_5m_cm": current_level - float(row_5m["water_level_cm"]),
        "water_rise_15m_cm": current_level - float(row_15m["water_level_cm"]),
        "missing_ratio_15m": missing_ratio,
    }
    return {name: round(float(features[name]), 4) for name in FEATURE_NAMES}, "valid"


def identify_main_factor(features: dict[str, float]) -> str:
    rain_heavy = features["rain_rate_mmh"] >= 30 or features["rain_sum_15m"] >= 8
    rising_fast = features["water_rise_5m_cm"] >= 2 or features["water_rise_15m_cm"] >= 4
    if rain_heavy and rising_fast:
        return "Mưa lớn và nước đang dâng nhanh"
    if rising_fast:
        return "Mực nước đang dâng nhanh"
    if rain_heavy:
        return "Cường độ mưa lớn"
    return "Mực nước và mưa đang ổn định"
