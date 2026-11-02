"""Check the shipped learned bundle directly; no training pipeline required."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from mini_flood.ai_settings import FEATURE_NAMES, load_ai_config
from mini_flood.config import MiniFloodSettings
from mini_flood.models import MiniFloodModelRegistry
from mini_flood_api import create_app


def test_packaged_bundle_matches_runtime_schema_and_hashes():
    config = load_ai_config("config/ai.demo.json")
    settings = MiniFloodSettings(ai=config, runtime_mode="demo", notification_worker_enabled=False)
    metadata = json.loads((settings.model_dir / "mini_flood_metadata.json").read_text())
    assert metadata["features"] == list(FEATURE_NAMES)
    assert metadata["feature_signature"] == config.feature_signature
    assert metadata["horizons_seconds"] == [15, 30, 60]
    for artifact in metadata["artifacts"].values():
        assert hashlib.sha256((settings.model_dir / artifact["file"]).read_bytes()).hexdigest() == artifact["sha256"]
    registry = MiniFloodModelRegistry(settings)
    assert registry.ready and registry.demo_approved
    assert not registry.promoted


def test_http_predicts_with_packaged_model_without_training_code(tmp_path, monkeypatch):
    config = load_ai_config("config/ai.demo.json")
    settings = MiniFloodSettings(ai=config, runtime_mode="demo", database_path=tmp_path / "runtime.sqlite3",
                                 notification_worker_enabled=False, mdns_enabled=False)
    app = create_app(settings)
    origin = datetime.now(timezone.utc)
    headers = {"X-Device-Key": settings.device_api_key}
    with TestClient(app) as client:
        for sequence in range(4):
            now = origin + timedelta(seconds=sequence * config.data.expected_interval_seconds)
            monkeypatch.setattr("mini_flood.service.utc_now", lambda now=now: now)
            response = client.post("/api/v2/telemetry", headers=headers, json={
                "device_id": settings.default_device_id, "boot_id": "packaged-model", "sequence_no": sequence,
                "timestamp": now.isoformat(), "schema_version": 2,
                "sample_interval_ms": config.data.expected_interval_seconds * 1000,
                "rain_interval_mm": 0.05, "rain_rate_mmh": 36, "water_level_cm": 10 + sequence,
                "quality_flags": [],
            })
            assert response.status_code == 200
            snapshot = client.get(f"/api/v2/stations/{settings.default_device_id}/snapshot", headers=headers).json()
            inference = snapshot["current_inference"]["inference"]
            assert inference["status"] == ("ready" if sequence == 3 else "warming_up")
        assert all(point["level_cm"] is not None for point in inference["forecasts"])
        assert inference["data_source"] == "synthetic"
        assert set(point["algorithm"] for point in inference["forecasts"]) == {"random_forest"}
        stations = client.get("/api/v2/stations", headers=headers).json()["items"]
        assert stations == [{
            "device_id": settings.default_device_id,
            "last_seen_at": snapshot["current_inference"]["server_timestamp"],
        }]


def test_synthetic_packaged_model_cannot_be_enabled_as_real():
    config = load_ai_config("config/ai.demo.json")
    registry = MiniFloodModelRegistry(MiniFloodSettings(ai=config, runtime_mode="real"))
    assert not registry.ready
    assert set(registry.errors.values()) == {"model_not_approved"}
