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
    "rain_sum_window_mm": 9,
    "water_level_cm": 20,
    "water_delta_window_cm": 3,
}


def evaluate(manager, timestamp, level_cm, features=None):
    current = dict(features or FEATURES)
    current["water_level_cm"] = min(current["water_level_cm"], level_cm)
    return manager.evaluate(
        None,
        "device",
        timestamp,
        {900: level_cm, 1800: level_cm},
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


def test_surge_update_when_water_rises_further(tmp_path, monkeypatch):
    monkeypatch.setenv("MINI_FLOOD_SURGE_STEP_CM", "5.0")
    monkeypatch.setenv("MINI_FLOOD_SURGE_COOLDOWN_SECONDS", "0.0")
    db = MiniFloodDatabase(tmp_path / "alerts.sqlite3")
    manager = AlertManager(db, MiniFloodSettings(database_path=tmp_path / "alerts.sqlite3"))

    f1 = dict(FEATURES, water_level_cm=41)
    level, alert_id_1 = evaluate(manager, "2026-10-17T09:00:00+07:00", 41, features=f1)
    assert level == 2
    assert alert_id_1 is not None

    # Small increase of 2 cm (43 cm) -> No surge update (below 5 cm threshold)
    f2 = dict(FEATURES, water_level_cm=43)
    level, alert_id_2 = evaluate(manager, "2026-10-17T09:00:10+07:00", 43, features=f2)
    assert level == 2
    assert alert_id_2 is None

    # Surge increase to 47 cm (>= 5 cm above 41 cm) -> Surge Update triggers!
    f3 = dict(FEATURES, water_level_cm=47)
    level, alert_id_3 = evaluate(manager, "2026-10-17T09:00:20+07:00", 47, features=f3)
    assert level == 2
    assert alert_id_3 is not None

    with db.connect() as conn:
        row = conn.execute("SELECT event_type, message FROM alert_events WHERE id = ?", (alert_id_3,)).fetchone()
        assert row["event_type"] == "surge_update"
        assert "🔴 CẬP NHẬT: NƯỚC TIẾP TỤC DÂNG CAO" in row["message"]

    # Verify recovery resets surge level properly
    evaluate(manager, "2026-10-17T09:01:00+07:00", 37, features=dict(FEATURES, water_level_cm=37))
    level, recovery_id = evaluate(manager, "2026-10-17T09:03:00+07:00", 37, features=dict(FEATURES, water_level_cm=37))
    assert level == 1
    assert recovery_id is not None
