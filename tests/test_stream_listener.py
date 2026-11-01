from listen_realtime_stream import format_forecasts


def test_listener_displays_configured_horizons_and_errors():
    formatted = format_forecasts({"forecasts": [
        {"horizon_seconds": 15, "level_cm": 25.2},
        {"horizon_seconds": 30, "level_cm": None, "error": "model_unavailable"},
        {"horizon_seconds": 60, "level_cm": 41.0},
    ]})
    assert "+15 giây: 25.2 cm" in formatted
    assert "+30 giây: model_unavailable" in formatted
    assert "+1 phút: 41.0 cm" in formatted
    assert "15m" not in formatted
