from datetime import datetime, timezone

import pytest

from simulate_iot_alert_thresholds import (
    build_payload,
    build_water_levels,
    extract_observation,
)


def test_build_water_levels_includes_warmup_and_sweep():
    assert build_water_levels(10, 16, 2, 4) == [10, 10, 10, 10, 12, 14, 16]
    with pytest.raises(ValueError):
        build_water_levels(10, 5, 1, 4)


def test_build_payload_matches_schema_v2_contract():
    payload = build_payload(
        device_id="qa-threshold",
        boot_id="boot-1",
        sequence_no=3,
        timestamp=datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc),
        interval_seconds=5,
        rain_rate_mmh=36,
        water_level_cm=25,
    )
    assert payload["schema_version"] == 2
    assert payload["sample_interval_ms"] == 5000
    assert payload["rain_interval_mm"] == 0.05
    assert payload["water_level_cm"] == 25
    assert payload["quality_flags"] == []


def test_extract_observation_uses_only_ready_finite_forecasts():
    event = {
        "water_level_cm": 35,
        "rain_rate_mmh": 36,
        "rain_interval_mm": 0.05,
        "quality_status": "valid",
        "alert_level": 1,
        "alert_label": "Cảnh báo",
        "alert_source": "model",
        "inference": {
            "status": "ready",
            "forecasts": [
                {"horizon_seconds": 15, "level_cm": 34, "status": "ready"},
                {"horizon_seconds": 30, "level_cm": 38, "status": "ready"},
                {"horizon_seconds": 60, "level_cm": None, "status": "prediction_failed"},
            ],
        },
    }
    observation = extract_observation(event)
    assert observation["forecasts"] == [(15, 34.0), (30, 38.0)]
    assert observation["rain_rate_mmh"] == 36
    assert observation["rain_interval_mm"] == 0.05
    assert observation["controlling_horizon"] == 30
    assert observation["max_forecast_cm"] == 38
    assert observation["alert_level"] == 1
