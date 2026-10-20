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
    """Tạo feature từ window <=5 phút gần nhất (inference window ngắn).

    Chỉ cần tối thiểu 3 bản ghi liên tục (~3 phút) là bắt đầu predict.
    Đây là dữ liệu INFERENCE, không phải training data.
    """
    if not rows:
        return None, "warming_up"

    ordered = sorted(rows, key=lambda row: (_parse_time(row["timestamp"]), int(row["sequence_no"])))
    current = ordered[-1]
    end = _parse_time(current["timestamp"])
    start_5 = end - timedelta(minutes=5)
    history_5 = [row for row in ordered if start_5 <= _parse_time(row["timestamp"]) <= end]

    # Cần ít nhất 3 bản ghi trong 5 phút gần nhất
    if len(history_5) < 3:
        return None, "warming_up"

    # water_rise_2m: so sánh với bản ghi gần T-2 phút nhất
    row_2m = _latest_at_or_before(ordered, end - timedelta(minutes=2))
    water_rise_2m = (float(current["water_level_cm"]) - float(row_2m["water_level_cm"])) if row_2m else 0.0

    current_level = float(current["water_level_cm"])
    features = {
        "rain_rate_mmh": float(current["rain_rate_mmh"]),
        "rain_sum_5m": _sum_window(ordered, end, 5),
        "water_level_cm": current_level,
        "water_rise_2m_cm": water_rise_2m,
    }
    return {name: round(float(features[name]), 4) for name in FEATURE_NAMES}, "valid"


def identify_main_factor(features: dict[str, float]) -> str:
    rain_heavy = features["rain_rate_mmh"] >= 30 or features["rain_sum_5m"] >= 4
    rising_fast = features["water_rise_2m_cm"] >= 1
    if rain_heavy and rising_fast:
        return "Mưa lớn và nước đang dâng nhanh"
    if rising_fast:
        return "Mực nước đang dâng nhanh"
    if rain_heavy:
        return "Cường độ mưa lớn"
    return "Mực nước và mưa đang ổn định"
