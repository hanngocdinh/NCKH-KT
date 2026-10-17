from mini_flood.config import MiniFloodSettings
from mini_flood.db import MiniFloodDatabase
from mini_flood.notifications import AlertManager, DeliveryWorker


def prediction(level: int):
    labels = {0: "An toàn", 1: "Cảnh báo", 2: "Nguy hiểm"}
    item = {"risk_level": level, "risk_label": labels[level], "probabilities": [0.1, 0.1, 0.8]}
    return {"15m": dict(item), "30m": dict(item)}


FEATURES = {
    "rain_rate_mmh": 40,
    "rain_sum_5m": 3,
    "rain_sum_15m": 9,
    "rain_sum_30m": 12,
    "water_level_cm": 20,
    "water_rise_5m_cm": 3,
    "water_rise_15m_cm": 6,
    "missing_ratio_15m": 0,
}


def test_escalation_is_queued_once_and_channels_are_independent(tmp_path):
    db = MiniFloodDatabase(tmp_path / "alerts.sqlite3")
    manager = AlertManager(db, MiniFloodSettings(database_path=tmp_path / "alerts.sqlite3"))
    alert_id = manager.evaluate(None, "device", "2026-10-17T09:00:00+07:00", prediction(2), FEATURES, "test")
    assert alert_id is not None
    assert manager.evaluate(None, "device", "2026-10-17T09:00:00+07:00", prediction(2), FEATURES, "test") is None

    sent = []

    def telegram(message):
        sent.append(("telegram", message))
        return True, ""

    def email(message):
        sent.append(("email", message))
        return False, "smtp down"

    worker = DeliveryWorker(db, telegram_sender=telegram, email_sender=email)
    assert worker.process_due() == 2
    assert {channel for channel, _ in sent} == {"telegram", "email"}
    with db.connect() as conn:
        statuses = {row["channel"]: row["status"] for row in conn.execute("SELECT channel, status FROM delivery_attempts")}
    assert statuses["telegram"] == "sent"
    assert statuses["email"] == "retry"


def test_recovery_requires_two_safe_cycles_and_survives_new_manager(tmp_path):
    path = tmp_path / "alerts.sqlite3"
    db = MiniFloodDatabase(path)
    settings = MiniFloodSettings(database_path=path)
    first = AlertManager(db, settings)
    assert first.evaluate(None, "device", "t1", prediction(1), FEATURES, "test") is not None

    second = AlertManager(MiniFloodDatabase(path), settings)
    assert second.evaluate(None, "device", "t2", prediction(0), FEATURES, "test") is None
    recovery_id = second.evaluate(None, "device", "t3", prediction(0), FEATURES, "test")
    assert recovery_id is not None
