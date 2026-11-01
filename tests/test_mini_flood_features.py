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
    assert status == "ready"
    assert features is not None
    assert set(features) == {
        "rain_rate_mmh",
        "rain_sum_window_mm",
        "water_level_cm",
        "water_delta_window_cm",
    }
    # 5 bản ghi trong 5 phút gần nhất, mỗi bản 1.0mm → rain_sum_window_mm = 5.0
    assert features["rain_sum_window_mm"] == pytest.approx(5.0)
    # row cuối water=40, row T-2m water=38 → rise = 2.0
    assert features["water_delta_window_cm"] == pytest.approx(2.0)


def test_build_features_requires_at_least_three_rows():
    """Warm-up: cần tối thiểu 3 bản ghi trong 5 phút."""
    features, status = build_features(make_rows(2))
    assert features is None
    assert status == "warming_up"


def test_missing_points_are_not_replaced_by_zero():
    rows = make_rows()
    # Xóa 3 bản ghi giữa, còn lại vẫn >= 3 bản trong window 5 phút
    rows = [row for row in rows if row["sequence_no"] not in {18, 19, 20}]
    features, status = build_features(rows)
    assert status == "ready"
    assert features is not None
    # Chỉ tính 5 phút gần nhất (5 bản ghi, mỗi bản 1.0mm)
    assert features["rain_sum_window_mm"] == pytest.approx(5.0)


def test_requires_complete_rain_window():
    features, status = build_features(make_rows(3))
    assert features is None
    assert status == "warming_up"


def test_gap_inside_window_and_invalid_flags_are_not_silently_removed():
    rows = [row for row in make_rows(8) if row["sequence_no"] != 5]
    assert build_features(rows)[0] is None
    rows = make_rows(8)
    rows[-2]["quality_flags"] = "invalid-json"
    assert build_features(rows)[1] == "invalid_input"
