from mini_flood.config import MiniFloodSettings
from mini_flood.db import MiniFloodDatabase
from mini_flood.notifications import AlertManager, DeliveryWorker


def prediction(level: int):
    labels = {0: "An toàn", 1: "Cảnh báo", 2: "Nguy hiểm"}
    item = {"risk_level": level, "risk_label": labels[level], "probabilities": [0.1, 0.1, 0.8]}
    return {"15m": dict(item), "30m": dict(item)}


FEATURES = {
    "rain_rate_mmh": 40,
    "rain_sum_5m": 9,
    "water_level_cm": 20,
    "water_rise_2m_cm": 3,
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


def test_check_telegram_connection_missing_credentials(monkeypatch):
    from mini_flood.notifications import check_telegram_connection

    monkeypatch.delenv("MINI_FLOOD_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("MINI_FLOOD_TELEGRAM_CHAT_ID", raising=False)

    ok, msg = check_telegram_connection(None, None)
    assert not ok
    assert "MINI_FLOOD_TELEGRAM_TOKEN" in msg

    ok, msg = check_telegram_connection("valid_token", None)
    assert not ok
    assert "MINI_FLOOD_TELEGRAM_CHAT_ID" in msg


def test_check_telegram_connection_success(monkeypatch):
    from mini_flood.notifications import check_telegram_connection

    class MockResponse:
        def __init__(self, status_code, json_data, text=""):
            self.status_code = status_code
            self._json_data = json_data
            self.text = text

        def json(self):
            return self._json_data

    import requests

    def mock_get(url, timeout=10):
        return MockResponse(200, {"result": {"username": "TestFloodBot"}})

    def mock_post(url, json=None, timeout=10):
        return MockResponse(200, {"ok": True})

    monkeypatch.setattr(requests, "get", mock_get)
    monkeypatch.setattr(requests, "post", mock_post)

    ok, msg = check_telegram_connection("fake_token", "123456")
    assert ok
    assert "TestFloodBot" in msg
    assert "123456" in msg


def test_check_telegram_connection_invalid_token(monkeypatch):
    from mini_flood.notifications import check_telegram_connection

    class MockResponse:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

    import requests

    def mock_get(url, timeout=10):
        return MockResponse(401, "Unauthorized")

    monkeypatch.setattr(requests, "get", mock_get)

    ok, msg = check_telegram_connection("bad_token", "123456")
    assert not ok
    assert "Token không hợp lệ" in msg
