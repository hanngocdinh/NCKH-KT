from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from mini_flood.config import MiniFloodSettings
from mini_flood_api import create_app


def make_client(tmp_path):
    settings = MiniFloodSettings(
        database_path=tmp_path / "mini.sqlite3",
        model_dir=tmp_path / "models",
        device_api_key="test-key",
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
        assert client.post("/api/v2/telemetry", json=payload(1, now)).status_code == 401
        response = client.post(
            "/api/v2/telemetry",
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
            response = client.post("/api/v2/telemetry", json=body, headers=headers)
            assert response.status_code == 200
            first = first or response.json()
            final = response.json()
        assert first["quality_status"] in {"unknown", "warming_up"}
        assert final["quality_status"] == "valid"
        assert "predictions" not in final
        latest = client.get(
            "/api/v2/stations/mini-flood-station-01/latest", headers=headers
        ).json()
        assert latest["forecast_15m_cm"] is not None
        assert latest["forecast_30m_cm"] is not None
        duplicate = client.post("/api/v2/telemetry", json=body, headers=headers).json()
        assert duplicate["duplicate"] is True
        assert "predictions" not in duplicate


def test_same_sequence_from_new_boot_is_not_duplicate(tmp_path):
    with make_client(tmp_path) as client:
        headers = {"X-Device-Key": "test-key"}
        first = payload(1, datetime.now(timezone.utc), water=8, rain=2)
        first["boot_id"] = "boot-a"
        assert client.post(
            "/api/v2/telemetry", json=first, headers=headers
        ).json()["duplicate"] is False
        assert client.post(
            "/api/v2/telemetry", json=first, headers=headers
        ).json()["duplicate"] is True

        restarted = payload(1, datetime.now(timezone.utc), water=9, rain=3)
        restarted["boot_id"] = "boot-b"
        response = client.post(
            "/api/v2/telemetry", json=restarted, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["duplicate"] is False
        latest = client.get(
            "/api/v2/stations/mini-flood-station-01/latest", headers=headers
        ).json()
        assert latest["boot_id"] == "boot-b"
        assert latest["sequence_no"] == 1


def test_current_danger_level_overrides_warmup(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v2/telemetry",
            json=payload(1, datetime.now(timezone.utc), water=42),
            headers={"X-Device-Key": "test-key"},
        )
        assert response.status_code == 200
        result = response.json()
        assert "predictions" not in result
        latest = client.get(
            "/api/v2/stations/mini-flood-station-01/latest",
            headers={"X-Device-Key": "test-key"},
        ).json()
        assert latest["safety_override"] == 1
        assert latest["alert_level"] == 2
        assert latest["forecast_15m_cm"] is None
        # notification_worker_enabled=False phải giữ delivery ở hàng đợi,
        # tuyệt đối không gọi Telegram/email thật trong lúc chạy test.
        db = client.app.state.service.db
        with db.connect() as conn:
            statuses = {
                row["status"]
                for row in conn.execute("SELECT status FROM delivery_attempts")
            }
        assert statuses == {"pending"}


def test_api_validation_and_health(tmp_path):
    with make_client(tmp_path) as client:
        body = payload(1, datetime.now(timezone.utc))
        body["water_level_cm"] = -1
        assert client.post(
            "/api/v2/telemetry", json=body, headers={"X-Device-Key": "test-key"}
        ).status_code == 422
        health = client.get("/api/v2/health")
        assert health.status_code == 200
        assert health.json()["simulation"] is True


def test_experiment_is_attached_and_exported(tmp_path):
    with make_client(tmp_path) as client:
        headers = {"X-Device-Key": "test-key"}
        started = client.post(
            "/api/v2/experiments/start",
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
            "/api/v2/telemetry",
            json=payload(10, datetime.now(timezone.utc)),
            headers=headers,
        )
        exported = client.get(
            "/api/v2/experiments/export.csv?device_id=mini-flood-station-01",
            headers=headers,
        )
        assert exported.status_code == 200
        assert "normal-run-01" in exported.text
        latest = client.get(
            "/api/v2/stations/mini-flood-station-01/latest", headers=headers
        ).json()
        assert latest["experiment_id"] == "normal-run-01"


def test_station_config_is_dynamic_and_validated(tmp_path):
    with make_client(tmp_path) as client:
        headers = {"X-Device-Key": "test-key"}
        url = "/api/v2/stations/mini-flood-station-01/config"
        initial = client.get(url, headers=headers).json()
        assert initial["overflow_level_cm"] == 40
        assert initial["warning_level_cm"] == 30

        updated = client.put(
            url,
            headers=headers,
            json={
                "overflow_level_cm": 60,
                "warning_margin_cm": 15,
                "hysteresis_cm": 2,
                "recovery_hold_seconds": 120,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["warning_level_cm"] == 45

        invalid = client.put(
            url,
            headers=headers,
            json={
                "overflow_level_cm": 20,
                "warning_margin_cm": 20,
                "hysteresis_cm": 2,
                "recovery_hold_seconds": 120,
            },
        )
        assert invalid.status_code == 422

        first = client.post(
            "/api/v2/telemetry",
            headers=headers,
            json=payload(100, datetime.now(timezone.utc), water=35),
        )
        assert first.status_code == 200
        latest = client.get(
            "/api/v2/stations/mini-flood-station-01/latest", headers=headers
        ).json()
        assert latest["alert_level"] == 0

        client.put(
            url,
            headers=headers,
            json={
                "overflow_level_cm": 40,
                "warning_margin_cm": 10,
                "hysteresis_cm": 2,
                "recovery_hold_seconds": 120,
            },
        )
        client.post(
            "/api/v2/telemetry",
            headers=headers,
            json=payload(101, datetime.now(timezone.utc), water=35),
        )
        latest = client.get(
            "/api/v2/stations/mini-flood-station-01/latest", headers=headers
        ).json()
        assert latest["alert_level"] == 1
