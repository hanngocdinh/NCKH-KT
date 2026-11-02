from datetime import datetime, timezone
from pathlib import Path

import requests
from streamlit.testing.v1 import AppTest


class FakeResponse:
    status_code = 200

    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


def telemetry_event(device_id: str, water_level: float) -> dict:
    stamp = datetime.now(timezone.utc).isoformat()
    return {
        "type": "telemetry",
        "device_id": device_id,
        "boot_id": "dashboard-test",
        "sequence_no": 1,
        "timestamp": stamp,
        "server_timestamp": stamp,
        "water_level_cm": water_level,
        "rain_rate_mmh": 12.0,
        "rain_interval_mm": 0.02,
        "rain_valid": True,
        "water_valid": True,
        "quality_status": "valid",
        "quality_flags": [],
        "is_live": True,
        "alert_level": 0,
        "alert_label": "An toàn",
        "alert_source": "model",
        "warning_level_cm": 30.0,
        "overflow_level_cm": 40.0,
        "inference": {
            "mode": "model",
            "status": "ready",
            "runtime_mode": "demo",
            "data_source": "synthetic",
            "forecasts": [
                {
                    "horizon_seconds": 15,
                    "level_cm": water_level + 1,
                    "status": "ready",
                }
            ],
        },
    }


def test_selecting_device_queries_its_snapshot_and_history(monkeypatch):
    calls: list[str] = []

    def fake_get(url, **_kwargs):
        calls.append(url)
        if url.endswith("/stations"):
            return FakeResponse({"items": [
                {"device_id": "device-a", "last_seen_at": "2026-11-02T10:00:00+00:00"},
                {"device_id": "device-b", "last_seen_at": "2026-11-02T09:00:00+00:00"},
            ]})
        if "/manual-device/" in url:
            device_id, water_level = "manual-device", 33.0
        elif "/device-b/" in url:
            device_id, water_level = "device-b", 22.0
        else:
            device_id, water_level = "device-a", 11.0
        event = telemetry_event(device_id, water_level)
        if url.endswith("/config"):
            return FakeResponse({
                "device_id": device_id,
                "overflow_level_cm": 40.0,
                "warning_margin_cm": 10.0,
                "hysteresis_cm": 2.0,
                "recovery_hold_seconds": 10,
                "warning_level_cm": 30.0,
            })
        if "/snapshot" in url:
            return FakeResponse({
                "last_received": event,
                "current_inference": event,
                "current_measurement": event,
            })
        if "/history" in url:
            return FakeResponse({"device_id": device_id, "items": [event]})
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(requests, "get", fake_get)
    app_path = Path(__file__).resolve().parents[1] / "app_mini_flood_dashboard.py"
    app = AppTest.from_file(str(app_path)).run(timeout=10)
    assert not app.exception
    assert app.selectbox[0].options == ["device-a", "device-b"]

    calls.clear()
    app.selectbox[0].select("device-b").run(timeout=10)
    assert not app.exception
    assert app.selectbox[0].value == "device-b"
    assert any("/stations/device-b/snapshot" in url for url in calls)
    assert any("/stations/device-b/history" in url for url in calls)
    assert app.metric[0].value == "22.0 cm"

    calls.clear()
    manual_app = AppTest.from_file(str(app_path))
    manual_app.session_state["selected_device_id"] = "manual-device"
    manual_app.run(timeout=10)
    assert not manual_app.exception
    assert manual_app.selectbox[0].value == "manual-device"
    assert "manual-device" in manual_app.selectbox[0].options
    assert any("/stations/manual-device/snapshot" in url for url in calls)
    assert any("/stations/manual-device/history" in url for url in calls)
    assert manual_app.metric[0].value == "33.0 cm"
