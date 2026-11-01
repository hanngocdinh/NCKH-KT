from mini_flood.dashboard_view import (
    forecast_horizon_seconds,
    forecast_level_cm,
    select_model_forecasts,
)


def test_dashboard_selects_only_ready_outputs_returned_by_model():
    inference = {
        "mode": "model",
        "forecasts": [
            {"horizon_seconds": 30, "level_cm": 14.2, "status": "ready"},
            {"horizon_seconds": 15, "level_cm": 13.9, "status": "ready"},
            {"horizon_seconds": 60, "level_cm": None, "status": "prediction_failed"},
        ],
    }
    selected, issues = select_model_forecasts(inference)
    assert list(selected) == [15, 30]
    assert selected[15]["level_cm"] == 13.9
    assert issues == ["forecast_60s_prediction_failed"]


def test_dashboard_does_not_create_or_overwrite_horizons():
    inference = {
        "mode": "model",
        "forecasts": [
            {"horizon_seconds": 15, "level_cm": 10, "status": "ready"},
            {"horizon_seconds": 15, "level_cm": 99, "status": "ready"},
            {"horizon_seconds": "bad", "level_cm": 20, "status": "ready"},
        ],
    }
    selected, issues = select_model_forecasts(inference)
    assert selected == {15: {"horizon_seconds": 15, "level_cm": 10.0, "status": "ready"}}
    assert issues == ["forecast_15s_duplicate", "forecast_2_invalid_horizon"]


def test_legacy_minute_unit_is_explicitly_converted_for_history_only():
    assert forecast_horizon_seconds({"horizon_minutes": 1}) == 60
    assert forecast_horizon_seconds({"horizon_seconds": 30, "horizon_minutes": 9}) == 30
    assert forecast_horizon_seconds({"horizon_seconds": 0}) is None
    assert forecast_level_cm({"level_cm": float("nan")}) is None


def test_non_model_inference_is_not_rendered_as_ai_output():
    selected, issues = select_model_forecasts(
        {"mode": "legacy", "forecasts": [{"horizon_seconds": 15, "level_cm": 10}]},
        require_ready=False,
    )
    assert selected == {}
    assert issues == ["inference_mode_not_model"]
