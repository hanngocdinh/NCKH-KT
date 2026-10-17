from datetime import datetime, timedelta, timezone

import pytest

from mini_flood.features import build_features


def make_rows(count: int = 31):
    start = datetime(2026, 10, 17, 1, 0, tzinfo=timezone.utc)
    return [
        {
            "device_id": "test-station",
            "sequence_no": i,
            "timestamp": (start + timedelta(minutes=i)).isoformat(),
            "rain_interval_mm": 1.0,
            "rain_rate_mmh": 60.0,
            "water_level_cm": 10.0 + i,
            "quality_status": "valid",
        }
        for i in range(count)
    ]


def test_build_features_uses_time_windows():
    features, status = build_features(make_rows())
    assert status == "valid"
    assert features is not None
    assert features["rain_sum_5m"] == pytest.approx(5.0)
    assert features["rain_sum_15m"] == pytest.approx(15.0)
    assert features["rain_sum_30m"] == pytest.approx(30.0)
    assert features["water_rise_5m_cm"] == pytest.approx(5.0)
    assert features["water_rise_15m_cm"] == pytest.approx(15.0)


def test_build_features_requires_fifteen_minutes_history():
    features, status = build_features(make_rows(10))
    assert features is None
    assert status == "warming_up"


def test_missing_points_are_reported_not_filled_with_zero():
    rows = make_rows()
    rows = [row for row in rows if row["sequence_no"] not in {18, 19, 20}]
    features, status = build_features(rows)
    assert status == "valid"
    assert features is not None
    assert features["missing_ratio_15m"] > 0
