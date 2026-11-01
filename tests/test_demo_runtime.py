"""Runtime-only tests: serving, model loading, snapshots, alerts and delivery."""
from datetime import datetime, timedelta, timezone
import asyncio
import json
import threading

import pytest
from fastapi.testclient import TestClient

from conftest import make_bundle
from mini_flood.ai_settings import FEATURE_NAMES, load_ai_config
from mini_flood.broadcaster import TelemetryBroadcaster
from mini_flood.config import MiniFloodSettings
from mini_flood.db import MiniFloodDatabase
from mini_flood.features import build_features
from mini_flood.models import MiniFloodModelRegistry
from mini_flood.notifications import DeliveryWorker
from mini_flood.schemas import TelemetryPayload
from mini_flood.service import MiniFloodService
from mini_flood_api import create_app


def demo_service(tmp_path, constant=35, runtime_mode="demo"):
    ai = load_ai_config("config/ai.demo.json")
    directory = tmp_path / "bundle"
    metadata = make_bundle(directory, ai, constant)
    metadata.update(data_source="synthetic", promoted=False, demo_approved=True, evaluation_schema="alert-replay-v2")
    (directory / "mini_flood_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    settings = MiniFloodSettings(ai=ai, model_dir=directory, database_path=tmp_path / "demo.sqlite3",
                                 runtime_mode=runtime_mode, mdns_enabled=False, notification_worker_enabled=False)
    return MiniFloodService(settings)


def sample(seq, stamp, water=10, flags=None, boot="demo"):
    return TelemetryPayload(device_id="mini-flood-station-01", boot_id=boot, sequence_no=seq,
                            timestamp=stamp, schema_version=2, sample_interval_ms=5000,
                            rain_interval_mm=0.1, rain_rate_mmh=72, water_level_cm=water, quality_flags=flags or [])


def feed(service, monkeypatch, count=4):
    start = datetime.now(timezone.utc)
    for seq in range(count):
        stamp = start + timedelta(seconds=seq * 5)
        monkeypatch.setattr("mini_flood.service.utc_now", lambda stamp=stamp: stamp)
        service.ingest(sample(seq, stamp))
    return start


def test_four_samples_ready_and_future_timestamps(tmp_path, monkeypatch):
    service = demo_service(tmp_path)
    start = feed(service, monkeypatch, count=3)
    assert service.snapshot("mini-flood-station-01")["current_inference"]["inference"]["status"] == "warming_up"
    stamp = start + timedelta(seconds=15)
    monkeypatch.setattr("mini_flood.service.utc_now", lambda: stamp)
    service.ingest(sample(3, stamp))
    item = service.snapshot("mini-flood-station-01")["current_inference"]
    assert item["inference"]["status"] == "ready"
    assert item["alert_source"] == "model"
    assert item["forecast_15m_cm"] is None
    assert [point["horizon_seconds"] for point in item["inference"]["forecasts"]] == [15, 30, 60]
    for point in item["inference"]["forecasts"]:
        assert datetime.fromisoformat(point["target_timestamp"]) == stamp + timedelta(seconds=point["horizon_seconds"])


def test_synthetic_cannot_load_in_real_mode(tmp_path):
    service = demo_service(tmp_path, runtime_mode="real")
    assert not service.registry.ready
    assert set(service.registry.errors.values()) == {"model_not_approved"}
    assert not service.registry.promoted


def test_corrupt_demo_artifact_still_fails_closed(tmp_path):
    service = demo_service(tmp_path)
    metadata = json.loads((service.settings.model_dir / "mini_flood_metadata.json").read_text())
    artifact = service.settings.model_dir / metadata["artifacts"]["15"]["file"]
    artifact.write_bytes(b"corrupt")
    registry = MiniFloodModelRegistry(service.settings)
    result = registry.predict_detailed(dict(zip(FEATURE_NAMES, [10, 1, 10, 1])))
    assert result["forecasts"][0]["level_cm"] is None
    assert result["status"] == "model_unavailable"


def test_snapshot_not_replaced_by_clock_error_or_buffered_packet(tmp_path, monkeypatch):
    service = demo_service(tmp_path)
    now = datetime.now(timezone.utc)
    service.ingest(sample(1, now))
    service.ingest(sample(2, now - timedelta(seconds=20), water=99))
    service.ingest(sample(3, datetime(1970, 1, 1, tzinfo=timezone.utc), water=99))
    snapshot = service.snapshot("mini-flood-station-01")
    assert snapshot["current_measurement"]["sequence_no"] == 1
    assert snapshot["last_received"]["sequence_no"] == 3
    assert not snapshot["alert_state"]


def test_transaction_rollback_then_retry_is_complete(tmp_path, monkeypatch):
    service = demo_service(tmp_path)
    original = service.db.save_inference_trace
    monkeypatch.setattr(service.db, "save_inference_trace", lambda *args: (_ for _ in ()).throw(RuntimeError("crash")))
    item = sample(1, datetime.now(timezone.utc), water=45)
    with pytest.raises(RuntimeError, match="crash"):
        service.ingest(item)
    with service.db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM alert_events").fetchone()[0] == 0
    monkeypatch.setattr(service.db, "save_inference_trace", original)
    assert service.ingest(item)["duplicate"] is False
    assert service.snapshot(item.device_id)["alert_state"]["alert_level"] == 2


def test_delivery_claim_prevents_two_workers_sending_same_item(tmp_path):
    db = MiniFloodDatabase(tmp_path / "queue.sqlite3")
    db.enqueue_alert(None, "demo", "unique", "test", 1, "message", channels=("telegram",))
    sent = []
    def sender(message):
        sent.append(message)
        return True, ""
    workers = [DeliveryWorker(db, telegram_sender=sender) for _ in range(2)]
    threads = [threading.Thread(target=worker.process_due) for worker in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sent == ["message"]


def test_expired_flood_message_is_not_sent(tmp_path, monkeypatch):
    db = MiniFloodDatabase(tmp_path / "expired.sqlite3")
    db.enqueue_alert(None, "demo", "old", "escalation", 2, "old danger", channels=("telegram",))
    later = datetime.now(timezone.utc) + timedelta(seconds=db.delivery_config.message_ttl_seconds + 1)
    monkeypatch.setattr("mini_flood.db.utc_now", lambda: later)
    sent = []
    assert DeliveryWorker(db, telegram_sender=lambda message: (sent.append(message) or True, "")).process_due() == 0
    assert not sent
    with db.connect() as connection:
        assert connection.execute("SELECT status FROM delivery_attempts").fetchone()[0] == "expired"


def test_cross_thread_stream_queue_resync():
    async def run():
        broadcaster = TelemetryBroadcaster(queue_size=1)
        queue = await broadcaster.subscribe()
        thread = threading.Thread(target=lambda: (broadcaster.publish_sync({"n": 1}), broadcaster.publish_sync({"n": 2})))
        thread.start()
        thread.join()
        await asyncio.sleep(0)
        item = await asyncio.wait_for(queue.get(), timeout=1)
        assert item == {"n": 2, "resync_required": True}
        await broadcaster.unsubscribe(queue)
    asyncio.run(run())


def test_snapshot_api_and_demo_health(tmp_path, monkeypatch):
    service = demo_service(tmp_path)
    app = create_app(service.settings)
    with TestClient(app) as client:
        headers = {"X-Device-Key": service.settings.device_api_key}
        assert client.get("/api/v2/stations/mini-flood-station-01/snapshot").status_code == 401
        assert client.post("/api/v2/telemetry", headers=headers, json=sample(1, datetime.now(timezone.utc)).model_dump(mode="json")).status_code == 200
        body = client.get("/api/v2/stations/mini-flood-station-01/snapshot", headers=headers).json()
        assert body["runtime_mode"] == "demo"
        health = client.get("/api/v2/health").json()
        assert health["model_demo_approved"] and not health["model_promoted"]
        assert health["forecast_horizons_seconds"] == [15, 30, 60]


def test_unconfigured_channels_do_not_make_network_calls(tmp_path, monkeypatch):
    for name in ("MINI_FLOOD_TELEGRAM_TOKEN", "MINI_FLOOD_TELEGRAM_CHAT_ID", "MINI_FLOOD_SMTP_HOST", "MINI_FLOOD_EMAIL_TO"):
        monkeypatch.delenv(name, raising=False)
    db = MiniFloodDatabase(tmp_path / "disabled.sqlite3")
    db.enqueue_alert(None, "demo", "disabled", "test", 1, "message")
    monkeypatch.setattr("requests.post", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("external request")))
    DeliveryWorker(db).process_due()
    with db.connect() as connection:
        assert {row[0] for row in connection.execute("SELECT status FROM delivery_attempts")} == {"disabled"}


def test_library_version_mismatch_rejects_demo_bundle(tmp_path):
    service = demo_service(tmp_path)
    path = service.settings.model_dir / "mini_flood_metadata.json"
    metadata = json.loads(path.read_text())
    metadata["library_versions"]["scikit_learn"] = "0.0.0"
    path.write_text(json.dumps(metadata))
    registry = MiniFloodModelRegistry(service.settings)
    assert not registry.ready
    assert set(registry.errors.values()) == {"library_version_mismatch"}


def test_actual_overflow_has_new_event_after_model_danger_without_spam(tmp_path, monkeypatch):
    service = demo_service(tmp_path, constant=45)
    origin = feed(service, monkeypatch)
    for seq, water in ((4, 42), (5, 39), (6, 42), (7, 37), (8, 42)):
        now = origin + timedelta(seconds=seq * 5)
        monkeypatch.setattr("mini_flood.service.utc_now", lambda now=now: now)
        service.ingest(sample(seq, now, water=water))
    with service.db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM alert_events WHERE event_type='sensor_overflow'").fetchone()[0] == 2
    assert service.snapshot("mini-flood-station-01")["alert_state"]["alert_source"] == "sensor_rule"
