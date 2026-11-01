"""Runtime contracts for learned forecasts, input quality, time and alerts."""
from datetime import datetime, timedelta, timezone
import json

import pytest
from pydantic import ValidationError

from conftest import make_bundle
from mini_flood.ai_settings import FEATURE_NAMES, AIConfig, load_ai_config
from mini_flood.config import MiniFloodSettings
from mini_flood.features import build_features, sensor_validity
from mini_flood.models import MiniFloodModelRegistry
from mini_flood.schemas import TelemetryPayload
from mini_flood.service import MiniFloodService


def make_service(tmp_path, learned=False, constant=None, config=None):
    cfg = config or load_ai_config()
    if learned:
        make_bundle(tmp_path / "models", cfg, constant)
    return MiniFloodService(MiniFloodSettings(
        database_path=tmp_path / "v3.sqlite3", model_dir=tmp_path / "models",
        ai=cfg, notification_worker_enabled=False, mdns_enabled=False))


def payload(seq, stamp, water=10.0, flags=None, boot="boot", rain=6.0):
    return TelemetryPayload(schema_version=1, device_id="mini-flood-station-01",
                            boot_id=boot, sequence_no=seq, timestamp=stamp,
                            rain_interval_mm=rain / 60, rain_rate_mmh=rain,
                            water_level_cm=water, quality_flags=flags or [])


def run_history(service, monkeypatch, water=10.0, flags=None):
    end = datetime.now(timezone.utc)
    for i in range(6):
        stamp = end - timedelta(minutes=5-i)
        monkeypatch.setattr("mini_flood.service.utc_now", lambda value=stamp: value)
        service.ingest(payload(i, stamp, water, flags))
    return service.db.latest("mini-flood-station-01")


def test_model_missing_never_falls_back_or_reports_safe(tmp_path, monkeypatch):
    service = make_service(tmp_path)
    latest = run_history(service, monkeypatch)
    assert latest["inference"]["status"] == "model_unavailable"
    assert all(item["level_cm"] is None for item in latest["inference"]["forecasts"])
    assert latest["alert_level"] is None
    assert latest["alert_source"] is None


def test_learned_prediction_and_trace_are_used_for_alert(tmp_path, monkeypatch):
    service = make_service(tmp_path, learned=True, constant=35)
    latest = run_history(service, monkeypatch)
    assert latest["inference"]["status"] == "ready"
    assert latest["alert_level"] == 1
    assert latest["alert_source"] == "model"
    assert all(item["level_cm"] == pytest.approx(35) for item in latest["inference"]["forecasts"])
    trace = latest["inference_trace"]
    assert trace["feature_names"] == list(FEATURE_NAMES)
    assert trace["feature_vector"] == [trace["features"][name] for name in FEATURE_NAMES]
    assert trace["config_hash"] == service.config.config_hash
    assert trace["raw_payload"]["timestamp"] is not None
    assert all(item["artifact_hash"] for item in trace["inference"]["forecasts"])
    assert all(item["upper_p90_cm"] is None for item in latest["inference"]["forecasts"])


def test_sensor_rule_works_when_rain_and_model_unavailable(tmp_path):
    service = make_service(tmp_path)
    service.ingest(payload(1, datetime.now(timezone.utc), 42, ["rain_sensor_unverified"]))
    latest = service.db.latest("mini-flood-station-01")
    assert latest["alert_source"] == "sensor_rule"
    assert latest["alert_level"] == 2
    assert all(item["level_cm"] is None for item in latest["inference"]["forecasts"])


def test_water_invalid_cannot_trigger_sensor_override(tmp_path):
    service = make_service(tmp_path)
    service.ingest(payload(1, datetime.now(timezone.utc), 42, ["water_sensor_invalid"]))
    latest = service.db.latest("mini-flood-station-01")
    assert latest["alert_level"] is None
    assert latest["inference"]["status"] == "invalid_input"


@pytest.mark.parametrize("stamp", [None, datetime(1970, 1, 1, tzinfo=timezone.utc)])
def test_bad_clock_preserves_raw_time_and_excludes_ai(tmp_path, stamp):
    service = make_service(tmp_path)
    service.ingest(payload(1, stamp))
    latest = service.db.latest("mini-flood-station-01")
    assert latest["timestamp_source"] == "server"
    assert "clock_invalid" in latest["quality_flags"]
    assert latest["inference"]["status"] == "invalid_input"
    assert latest["inference_trace"]["feature_vector"] is None


def test_missing_model_does_not_lower_existing_alert(tmp_path, monkeypatch):
    service = make_service(tmp_path)
    end = datetime.now(timezone.utc)
    service.ingest(payload(100, end, 42))
    future = end + timedelta(minutes=5)
    monkeypatch.setattr("mini_flood.service.utc_now", lambda: future)
    service.ingest(payload(101, future, 10))
    latest = service.db.latest("mini-flood-station-01")
    assert latest["alert_level"] == 2
    assert latest["alert_source"] == "sensor_rule"


def test_stale_or_out_of_order_packets_cannot_escalate(tmp_path):
    service = make_service(tmp_path)
    now = datetime.now(timezone.utc)
    service.ingest(payload(10, now, 10))
    service.ingest(payload(11, now - timedelta(minutes=10), 99))
    service.ingest(payload(9, now - timedelta(seconds=10), 99))
    assert service.db.get_state("alert_state:mini-flood-station-01", {}) == {}
    with service.db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM inference_runs").fetchone()[0] == 3


def test_duplicate_does_not_create_second_inference(tmp_path):
    service = make_service(tmp_path)
    item = payload(1, datetime.now(timezone.utc), 42)
    service.ingest(item)
    assert service.ingest(item)["duplicate"] is True
    with service.db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM inference_runs").fetchone()[0] == 1


def test_timezone_and_boot_isolation(tmp_path, monkeypatch):
    service = make_service(tmp_path, learned=True)
    latest = run_history(service, monkeypatch)
    end = datetime.fromisoformat(latest["timestamp"])
    stamp = (end + timedelta(minutes=1)).astimezone(timezone(timedelta(hours=7)))
    monkeypatch.setattr("mini_flood.service.utc_now", lambda: stamp.astimezone(timezone.utc))
    service.ingest(payload(1, stamp, boot="new-boot"))
    latest = service.db.latest("mini-flood-station-01")
    assert latest["inference"]["status"] == "warming_up"
    assert latest["timestamp"].endswith("+00:00")


def test_unknown_quality_flags_fail_closed():
    assert sensor_validity({"quality_flags": "bad-json"}) == (False, False)
    assert sensor_validity({"quality_flags": ["new_unknown_fault"]}) == (False, False)


def test_config_validation_and_feature_signature():
    cfg = load_ai_config()
    raw = cfg.model_dump(mode="json")
    raw["data"]["max_gap_seconds"] = 1
    with pytest.raises(ValidationError):
        AIConfig.model_validate(raw)
    changed = cfg.model_copy(update={"data": cfg.data.model_copy(update={"rain_window_seconds": 600})})
    assert changed.feature_signature != cfg.feature_signature


@pytest.mark.parametrize("damage", ["hash", "missing", "metadata", "signature", "horizon", "not_approved", "deserialize", "artifact_features"])
def test_artifact_rejection_never_computes_fallback(tmp_path, damage):
    cfg = load_ai_config()
    model_dir = tmp_path / "models"
    meta = make_bundle(model_dir, cfg)
    h = cfg.horizons_seconds[0]
    if damage == "hash":
        (model_dir / meta["artifacts"][str(h)]["file"]).write_bytes(b"broken")
    elif damage == "missing":
        # Point to a nonexistent path rather than deleting artifacts.
        meta["artifacts"][str(h)]["file"] = "missing.joblib"
    elif damage == "signature":
        meta["feature_signature"] = "wrong"
    elif damage == "horizon":
        meta["horizons_seconds"] = [30]
    elif damage == "not_approved":
        meta["promoted"] = False
    elif damage in {"deserialize", "artifact_features"}:
        import joblib
        import hashlib
        artifact = model_dir / meta["artifacts"][str(h)]["file"]
        if damage == "deserialize":
            artifact.write_bytes(b"invalid serialization")
        else:
            model = joblib.load(artifact)
            model.feature_names_in_ = ["wrong_feature"]
            joblib.dump(model, artifact)
        meta["artifacts"][str(h)]["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    (model_dir / "mini_flood_metadata.json").write_text(
        "broken" if damage == "metadata" else json.dumps(meta), encoding="utf-8")
    registry = MiniFloodModelRegistry(MiniFloodSettings(model_dir=model_dir, ai=cfg))
    result = registry.predict_detailed(dict(zip(FEATURE_NAMES, [2, 1, 10, 1])))
    assert result["forecasts"][0]["level_cm"] is None
    assert result["forecasts"][0]["error"]
    assert result["status"] == "model_unavailable"


def test_prediction_exception_is_explicit_and_per_horizon(tmp_path):
    service = make_service(tmp_path, learned=True)
    class Broken:
        def predict(self, _):
            raise ValueError("test failure")
    service.registry.models[service.config.horizons_seconds[0]] = Broken()
    result = service.registry.predict_detailed(dict(zip(FEATURE_NAMES, [2, 1, 10, 1])))
    assert result["status"] == "prediction_failed"
    assert result["forecasts"][0]["level_cm"] is None
    assert "test failure" in result["forecasts"][0]["error"]
    assert result["forecasts"][1]["level_cm"] is not None


def test_configurable_horizon_is_served_from_bundle(tmp_path, monkeypatch):
    cfg = load_ai_config().model_copy(update={"horizons_seconds": (7,)})
    service = make_service(tmp_path, learned=True, constant=35, config=cfg)
    latest = run_history(service, monkeypatch)
    assert [item["horizon_seconds"] for item in latest["inference"]["forecasts"]] == [7]


def test_missing_device_data_is_alerted_once_and_recovers(tmp_path):
    service = make_service(tmp_path)
    service.ingest(payload(1, datetime.now(timezone.utc)))
    old = (datetime.now(timezone.utc) - timedelta(seconds=service.config.data.offline_timeout_seconds + 1)).isoformat()
    with service.db.connect() as conn:
        conn.execute("UPDATE telemetry SET server_timestamp = ?", (old,))
    assert service.alerts.check_device_liveness(service.config.data.offline_timeout_seconds) == 1
    assert service.alerts.check_device_liveness(service.config.data.offline_timeout_seconds) == 0
    service.ingest(payload(2, datetime.now(timezone.utc)))
    with service.db.connect() as conn:
        types = {row["event_type"] for row in conn.execute("SELECT event_type FROM alert_events")}
    assert {"device_offline", "device_recovery"} <= types


def test_sensor_below_overflow_does_not_override_model(tmp_path, monkeypatch):
    service = make_service(tmp_path, learned=True, constant=10)
    latest = run_history(service, monkeypatch, water=35)
    assert latest["alert_level"] == 0
    assert latest["alert_source"] == "model"


def test_partial_model_can_raise_but_not_lower_alert(tmp_path, monkeypatch):
    service = make_service(tmp_path, learned=True, constant=35)
    service.registry.models.pop(service.config.horizons_seconds[0])
    latest = run_history(service, monkeypatch)
    assert latest["inference"]["status"] == "model_unavailable"
    assert latest["alert_level"] == 1
    assert latest["alert_source"] == "model"


def test_rain_fault_stops_model_even_with_full_history(tmp_path, monkeypatch):
    service = make_service(tmp_path, learned=True, constant=35)
    latest = run_history(service, monkeypatch, flags=["rain_sensor_unverified"])
    assert latest["inference"]["status"] == "invalid_input"
    assert all(item["level_cm"] is None for item in latest["inference"]["forecasts"])
    assert latest["alert_level"] is None
