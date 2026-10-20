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
FEATURES = {
    "rain_rate_mmh": 40,
    "rain_sum_5m": 9,
    "water_level_cm": 20,
    "water_rise_2m_cm": 3,
}


def evaluate(manager, timestamp, level_cm, features=None):
    current = dict(features or FEATURES)
    current["water_level_cm"] = min(current["water_level_cm"], level_cm)
    return manager.evaluate(
        None,
        "device",
        timestamp,
        {15: level_cm, 30: level_cm},
        current,
        STATION,
        "test",
    )


def test_escalation_is_queued_once_and_channels_are_independent(tmp_path):
    db = MiniFloodDatabase(tmp_path / "alerts.sqlite3")
    manager = AlertManager(db, MiniFloodSettings(database_path=tmp_path / "alerts.sqlite3"))
    level, alert_id = evaluate(manager, "2026-10-17T09:00:00+07:00", 42)
    assert level == 2
    assert alert_id is not None
    level, duplicate_id = evaluate(manager, "2026-10-17T09:01:00+07:00", 42)
    assert level == 2
    assert duplicate_id is None

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
    assert "Dự báo 15 phút: 42.0 cm" in sent[0][1]
    assert "Mức tràn: 40.0 cm" in sent[0][1]
    with db.connect() as conn:
        statuses = {
            row["channel"]: row["status"]
            for row in conn.execute("SELECT channel, status FROM delivery_attempts")
        }
    assert statuses == {"telegram": "sent", "email": "retry"}


def test_hysteresis_uses_two_minutes_and_lowers_one_level(tmp_path):
    path = tmp_path / "alerts.sqlite3"
    db = MiniFloodDatabase(path)
    settings = MiniFloodSettings(database_path=path)
    first = AlertManager(db, settings)
    assert evaluate(first, "2026-10-17T09:00:00+07:00", 42)[0] == 2

    second = AlertManager(MiniFloodDatabase(path), settings)
    assert evaluate(second, "2026-10-17T09:01:00+07:00", 37)[0] == 2
    level, alert_id = evaluate(second, "2026-10-17T09:03:00+07:00", 37)
    assert level == 1
    assert alert_id is not None

    assert evaluate(second, "2026-10-17T09:04:00+07:00", 27)[0] == 1
    assert evaluate(second, "2026-10-17T09:06:00+07:00", 27)[0] == 0


def test_hysteresis_timer_resets_when_level_rebounds(tmp_path):
    db = MiniFloodDatabase(tmp_path / "alerts.sqlite3")
    manager = AlertManager(db, MiniFloodSettings(database_path=tmp_path / "alerts.sqlite3"))
    evaluate(manager, "2026-10-17T09:00:00+07:00", 42)
    evaluate(manager, "2026-10-17T09:01:00+07:00", 37)
    evaluate(manager, "2026-10-17T09:02:00+07:00", 39)
    assert evaluate(manager, "2026-10-17T09:03:00+07:00", 37)[0] == 2
    assert evaluate(manager, "2026-10-17T09:04:59+07:00", 37)[0] == 2


def test_check_telegram_connection_missing_credentials(monkeypatch):
    from mini_flood.notifications import check_telegram_connection

    monkeypatch.delenv("MINI_FLOOD_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("MINI_FLOOD_TELEGRAM_CHAT_ID", raising=False)
    ok, msg = check_telegram_connection(None, None)
    assert not ok and "MINI_FLOOD_TELEGRAM_TOKEN" in msg
    ok, msg = check_telegram_connection("valid_token", None)
    assert not ok and "MINI_FLOOD_TELEGRAM_CHAT_ID" in msg


def test_check_telegram_connection_success(monkeypatch):
    from mini_flood.notifications import check_telegram_connection

    class MockResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"result": {"username": "TestFloodBot"}}

    import requests

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: MockResponse())
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: MockResponse())
    ok, msg = check_telegram_connection("fake_token", "123456")
    assert ok and "TestFloodBot" in msg and "123456" in msg


def test_check_telegram_connection_invalid_token(monkeypatch):
    from mini_flood.notifications import check_telegram_connection

    class MockResponse:
        status_code = 401
        text = "Unauthorized"

    import requests

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: MockResponse())
    ok, msg = check_telegram_connection("bad_token", "123456")
    assert not ok and "Token không hợp lệ" in msg
