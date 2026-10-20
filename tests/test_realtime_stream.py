from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mini_flood.config import MiniFloodSettings
from mini_flood_api import create_app


@pytest.fixture
def test_client(tmp_path: Path):
    settings = MiniFloodSettings(
        database_path=tmp_path / "test_stream.sqlite3",
        model_dir=tmp_path / "models",
        device_api_key="test-key",
        notification_worker_enabled=False,
    )
    app = create_app(settings)
    return TestClient(app)


def test_health_includes_subscribers_count(test_client: TestClient):
    resp = test_client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "active_subscribers" in data
    assert data["active_subscribers"] == 0


def test_websocket_streaming_receives_telemetry_event(test_client: TestClient):
    with test_client.websocket_connect("/api/v1/stream/ws") as websocket:
        # Nhận tin nhắn chào mừng kết nối
        welcome = websocket.receive_json()
        assert welcome["type"] == "connected"
        assert welcome["status"] == "ok"

        # Gửi telemetry payload qua HTTP POST
        payload = {
            "schema_version": 1,
            "device_id": "mini-flood-station-01",
            "sequence_no": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rain_interval_mm": 0.5,
            "rain_rate_mmh": 30.0,
            "water_level_cm": 12.5,
            "quality_flags": [],
        }
        post_resp = test_client.post(
            "/api/v1/telemetry",
            json=payload,
            headers={"X-Device-Key": "test-key"},
        )
        assert post_resp.status_code == 200

        # WebSocket phải nhận được event telemetry phát ra ngay lập tức
        event = websocket.receive_json()
        assert event["type"] == "telemetry"
        assert event["device_id"] == "mini-flood-station-01"
        assert event["water_level_cm"] == pytest.approx(12.5)
        assert event["rain_rate_mmh"] == pytest.approx(30.0)


def test_websocket_ping_pong(test_client: TestClient):
    with test_client.websocket_connect("/api/v1/stream/ws") as websocket:
        websocket.receive_json()  # welcome
        websocket.send_text("ping")
        reply = websocket.receive_text()
        assert reply == "pong"
