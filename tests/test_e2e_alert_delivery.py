from datetime import datetime, timedelta, timezone

from mini_flood.config import MiniFloodSettings
from mini_flood.db import MiniFloodDatabase
from mini_flood.notifications import AlertManager, DeliveryWorker


STATION = {
    "overflow_level_cm": 40.0,
    "warning_margin_cm": 10.0,
    "warning_level_cm": 30.0,
    "hysteresis_cm": 2.0,
    "recovery_hold_seconds": 120,
}
DUMMY_FEATURES = {
    "rain_rate_mmh": 50.0,
    "rain_sum_5m": 12.0,
    "water_level_cm": 28.0,
    "water_rise_2m_cm": 5.0,
}


def evaluate(manager, timestamp, forecast):
    return manager.evaluate(
        telemetry_id=None,
        device_id="mini-flood-station-01",
        timestamp=timestamp,
        forecasts={15: forecast, 30: forecast},
        features=DUMMY_FEATURES,
        station=STATION,
        main_factor="Mưa lớn và nước đang dâng nhanh",
    )


def test_channels_independent(tmp_path):
    db_path = tmp_path / "alerts_e2e.sqlite3"
    db = MiniFloodDatabase(db_path)
    manager = AlertManager(db, MiniFloodSettings(database_path=db_path))
    level, alert_id = evaluate(manager, "2026-10-17T10:00:00+07:00", 42)
    assert level == 2 and alert_id is not None

    calls = []

    def mock_telegram(msg: str):
        calls.append(("telegram", msg))
        return True, ""

    def mock_email(msg: str):
        calls.append(("email", msg))
        return False, "SMTP connection refused"

    worker = DeliveryWorker(db, telegram_sender=mock_telegram, email_sender=mock_email)
    assert worker.process_due() == 2
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT channel, attempt_count, status, last_error FROM delivery_attempts WHERE alert_event_id = ?",
            (alert_id,),
        ).fetchall()
    statuses = {row["channel"]: dict(row) for row in rows}
    assert statuses["telegram"]["status"] == "sent"
    assert statuses["email"]["status"] == "retry"
    assert "SMTP connection refused" in statuses["email"]["last_error"]


def test_reminder_fires_after_30_min(tmp_path):
    db_path = tmp_path / "reminder_e2e.sqlite3"
    db = MiniFloodDatabase(db_path)
    manager = AlertManager(db, MiniFloodSettings(database_path=db_path, reminder_minutes=30))
    _, first_id = evaluate(manager, "2026-10-17T10:00:00+07:00", 42)
    _, immediate_id = evaluate(manager, "2026-10-17T10:01:00+07:00", 42)
    assert first_id is not None and immediate_id is None

    state = db.get_state("alert_state:mini-flood-station-01")
    state["last_danger_alert_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=35)
    ).isoformat()
    db.set_state("alert_state:mini-flood-station-01", state)
    _, reminder_id = evaluate(manager, "2026-10-17T10:36:00+07:00", 42)
    assert reminder_id is not None and reminder_id != first_id
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM alert_events WHERE id = ?", (reminder_id,)).fetchone()
    assert row["event_type"] == "reminder"
    assert row["alert_level"] == 2


def test_dynamic_threshold_changes_alert_decision(tmp_path):
    path = tmp_path / "dynamic.sqlite3"
    db = MiniFloodDatabase(path)
    manager = AlertManager(db, MiniFloodSettings(database_path=path))
    level, _ = evaluate(manager, "2026-10-17T10:00:00+07:00", 35)
    assert level == 1

    taller_station = dict(STATION, overflow_level_cm=60.0, warning_level_cm=45.0)
    other = AlertManager(MiniFloodDatabase(tmp_path / "other.sqlite3"), MiniFloodSettings())
    level, alert_id = other.evaluate(
        None,
        "mini-flood-station-01",
        "2026-10-17T10:00:00+07:00",
        {15: 35.0, 30: 35.0},
        DUMMY_FEATURES,
        taller_station,
        "test",
    )
    assert level == 0 and alert_id is None
