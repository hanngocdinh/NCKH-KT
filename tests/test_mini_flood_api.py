from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from mini_flood.config import MiniFloodSettings
from mini_flood_api import create_app


def make_client(tmp_path):
    settings = MiniFloodSettings(
        database_path=tmp_path / "mini.sqlite3",
        model_dir=tmp_path / "models",
        device_api_key="test-key",
        warning_level_cm=15,
        danger_level_cm=25,
        notification_worker_enabled=False,
    )
    return TestClient(create_app(settings))


def payload(sequence: int, timestamp: datetime, water: float = 10.0, rain: float = 2.0):
    return {
        "schema_version": 1,
        "device_id": "mini-flood-station-01",
        "sequence_no": sequence,
        "timestamp": timestamp.isoformat(),
        "rain_interval_mm": rain / 60.0,
        "rain_rate_mmh": rain,
        "water_level_cm": water,
        "quality_flags": [],
    }


def test_api_rejects_missing_or_wrong_key(tmp_path):
    with make_client(tmp_path) as client:
        now = datetime.now(timezone.utc)
        assert client.post("/api/v1/telemetry", json=payload(1, now)).status_code == 401
        response = client.post(
            "/api/v1/telemetry",
            json=payload(1, now),
            headers={"X-Device-Key": "wrong"},
        )
        assert response.status_code == 401


def test_api_warms_up_then_predicts_and_deduplicates(tmp_path):
    with make_client(tmp_path) as client:
        end = datetime.now(timezone.utc)
        headers = {"X-Device-Key": "test-key"}
        first = None
        final = None
        for sequence in range(17):
            stamp = end - timedelta(minutes=16 - sequence)
            body = payload(sequence, stamp, water=8 + sequence * 0.4, rain=20)
            response = client.post("/api/v1/telemetry", json=body, headers=headers)
            assert response.status_code == 200
            first = first or response.json()
            final = response.json()
        assert first["quality_status"] in {"unknown", "warming_up"}
        assert final["quality_status"] == "valid"
        assert "predictions" not in final
        latest = client.get(
            "/api/v1/stations/mini-flood-station-01/latest", headers=headers
        ).json()
        assert latest["risk_15m"] is not None
        assert latest["risk_30m"] is not None
        duplicate = client.post("/api/v1/telemetry", json=body, headers=headers).json()
        assert duplicate["duplicate"] is True
        assert "predictions" not in duplicate


def test_current_danger_level_overrides_warmup(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/telemetry",
            json=payload(1, datetime.now(timezone.utc), water=30),
            headers={"X-Device-Key": "test-key"},
        )
        assert response.status_code == 200
        result = response.json()
        assert "predictions" not in result
        latest = client.get(
            "/api/v1/stations/mini-flood-station-01/latest",
            headers={"X-Device-Key": "test-key"},
        ).json()
        assert latest["rule_override"] == 1
        assert latest["risk_15m"] == 2
        assert latest["risk_30m"] == 2


def test_api_validation_and_health(tmp_path):
    with make_client(tmp_path) as client:
        body = payload(1, datetime.now(timezone.utc))
        body["water_level_cm"] = -1
        assert client.post(
            "/api/v1/telemetry", json=body, headers={"X-Device-Key": "test-key"}
        ).status_code == 422
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["simulation"] is True


def test_experiment_is_attached_and_exported(tmp_path):
    with make_client(tmp_path) as client:
        headers = {"X-Device-Key": "test-key"}
        started = client.post(
            "/api/v1/experiments/start",
            json={
                "device_id": "mini-flood-station-01",
                "experiment_id": "normal-run-01",
                "scenario": "normal",
            },
            headers=headers,
        )
        assert started.status_code == 200
        assert started.json()["active"] is True
        client.post(
            "/api/v1/telemetry",
            json=payload(10, datetime.now(timezone.utc)),
            headers=headers,
        )
        exported = client.get(
            "/api/v1/experiments/export.csv?device_id=mini-flood-station-01",
            headers=headers,
        )
        assert exported.status_code == 200
        assert "normal-run-01" in exported.text
        latest = client.get(
            "/api/v1/stations/mini-flood-station-01/latest", headers=headers
        ).json()
        assert latest["experiment_id"] == "normal-run-01"
