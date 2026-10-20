import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from mini_flood.config import MiniFloodSettings
from mini_flood.db import MiniFloodDatabase
from mini_flood.notifications import AlertManager, DeliveryWorker


def make_dummy_prediction(level: int):
    labels = {0: "An toàn", 1: "Cảnh báo", 2: "Nguy hiểm"}
    item = {"risk_level": level, "risk_label": labels[level], "probabilities": [0.05, 0.15, 0.8]}
    return {"15m": dict(item), "30m": dict(item)}


DUMMY_FEATURES = {
    "rain_rate_mmh": 50.0,
    "rain_sum_5m": 12.0,
    "water_level_cm": 28.0,
    "water_rise_2m_cm": 5.0,
}


def test_channels_independent(tmp_path):
    """Kiểm tra hai kênh Telegram và Email xử lý hoàn toàn độc lập.
    Khi Email gặp sự cố (ví dụ SMTP timeout), Telegram vẫn gửi thành công,
    và trạng thái từng kênh được ghi nhận chính xác trong SQLite.
    """
    db_path = tmp_path / "alerts_e2e.sqlite3"
    db = MiniFloodDatabase(db_path)
    settings = MiniFloodSettings(database_path=db_path)
    manager = AlertManager(db, settings)

    # 1. Kích hoạt một cảnh báo nguy hiểm Mức 2
    alert_id = manager.evaluate(
        telemetry_id=None,
        device_id="mini-flood-station-01",
        timestamp="2026-10-17T10:00:00+07:00",
        predictions=make_dummy_prediction(2),
        features=DUMMY_FEATURES,
        main_factor="Mực nước đã vượt ngưỡng nguy hiểm",
    )
    assert alert_id is not None

    calls = []

    def mock_telegram(msg: str):
        calls.append(("telegram", msg))
        return True, ""

    def mock_email(msg: str):
        calls.append(("email", msg))
        return False, "SMTP connection refused: host unreachable"

    worker = DeliveryWorker(db, telegram_sender=mock_telegram, email_sender=mock_email)
    processed = worker.process_due()
    assert processed == 2
    assert len(calls) == 2

    # 2. Xác thực trạng thái độc lập trong cơ sở dữ liệu
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT channel, attempt_count, status, last_error FROM delivery_attempts WHERE alert_event_id = ?",
            (alert_id,),
        ).fetchall()
        statuses = {r["channel"]: dict(r) for r in rows}

    assert statuses["telegram"]["status"] == "sent"
    assert statuses["telegram"]["attempt_count"] == 1
    assert statuses["telegram"]["last_error"] is None

    assert statuses["email"]["status"] == "retry"
    assert statuses["email"]["attempt_count"] == 1
    assert "SMTP connection refused" in statuses["email"]["last_error"]


def test_reminder_fires_after_30_min(tmp_path):
    """Kiểm tra cơ chế nhắc lại (reminder):
    - Khi duy trì ở Mức 2 nguy hiểm cao, trong vòng 30 phút không gửi cảnh báo trùng lặp.
    - Sau khi đã quá 30 phút, một alert reminder được kích hoạt và enqueue vào DB.
    """
    db_path = tmp_path / "reminder_e2e.sqlite3"
    db = MiniFloodDatabase(db_path)
    settings = MiniFloodSettings(database_path=db_path, reminder_minutes=30)
    manager = AlertManager(db, settings)
    dev_id = "mini-flood-station-01"

    # Lần 1: Escalation Mức 2 ban đầu
    id_1 = manager.evaluate(
        telemetry_id=None,
        device_id=dev_id,
        timestamp="2026-10-17T10:00:00+07:00",
        predictions=make_dummy_prediction(2),
        features=DUMMY_FEATURES,
        main_factor="Mực nước đã vượt ngưỡng nguy hiểm",
    )
    assert id_1 is not None

    # Lần 2 (ngay sau đó 1 phút): Vẫn ở Mức 2 -> Không gửi lại (chống spam)
    id_immediate = manager.evaluate(
        telemetry_id=None,
        device_id=dev_id,
        timestamp="2026-10-17T10:01:00+07:00",
        predictions=make_dummy_prediction(2),
        features=DUMMY_FEATURES,
        main_factor="Mực nước đã vượt ngưỡng nguy hiểm",
    )
    assert id_immediate is None

    # Giả lập thời gian đã trôi qua 35 phút (> 30 phút quy định reminder)
    state = db.get_state(f"alert_state:{dev_id}")
    state["last_danger_alert_at"] = (datetime.now(timezone.utc) - timedelta(minutes=35)).isoformat()
    db.set_state(f"alert_state:{dev_id}", state)

    # Lần 3: Đã đủ điều kiện nhắc nhở -> Enqueue reminder
    id_reminder = manager.evaluate(
        telemetry_id=None,
        device_id=dev_id,
        timestamp="2026-10-17T10:36:00+07:00",
        predictions=make_dummy_prediction(2),
        features=DUMMY_FEATURES,
        main_factor="Mực nước vẫn ở mức nguy hiểm sau 30 phút",
    )
    assert id_reminder is not None
    assert id_reminder != id_1

    with db.connect() as conn:
        row = conn.execute("SELECT * FROM alert_events WHERE id = ?", (id_reminder,)).fetchone()
        assert row is not None
        assert row["event_type"] == "reminder"
        assert row["risk_level"] == 2


def test_recovery_needs_two_safe_cycles(tmp_path):
    """Kiểm tra quy tắc chuyển trạng thái hồi phục (recovery):
    - Sau khi cảnh báo Mức 2 hoặc Mức 1, nếu dữ liệu đo trở về Mức 0 (An toàn):
      + Chu kỳ Safe đầu tiên: Chưa gửi recovery (để chống dao động ranh giới).
      + Chu kỳ Safe thứ hai liên tiếp: Kích hoạt alert recovery thông báo đã an toàn.
    """
    db_path = tmp_path / "recovery_e2e.sqlite3"
    db = MiniFloodDatabase(db_path)
    settings = MiniFloodSettings(database_path=db_path)
    manager = AlertManager(db, settings)
    dev_id = "mini-flood-station-01"

    safe_features = dict(DUMMY_FEATURES)
    safe_features["water_level_cm"] = 8.0
    safe_features["rain_rate_mmh"] = 0.0

    # 1. Trạng thái nguy hiểm Mức 2
    alert_danger = manager.evaluate(
        telemetry_id=None,
        device_id=dev_id,
        timestamp="2026-10-17T11:00:00+07:00",
        predictions=make_dummy_prediction(2),
        features=DUMMY_FEATURES,
        main_factor="Mực nước vượt ngưỡng",
    )
    assert alert_danger is not None

    # 2. Chu kỳ An toàn lần 1 -> Không sinh cảnh báo recovery
    alert_safe_1 = manager.evaluate(
        telemetry_id=None,
        device_id=dev_id,
        timestamp="2026-10-17T11:01:00+07:00",
        predictions=make_dummy_prediction(0),
        features=safe_features,
        main_factor="Mực nước đã hạ",
    )
    assert alert_safe_1 is None

    # 3. Chu kỳ An toàn lần 2 liên tiếp -> Kích hoạt recovery alert
    alert_safe_2 = manager.evaluate(
        telemetry_id=None,
        device_id=dev_id,
        timestamp="2026-10-17T11:02:00+07:00",
        predictions=make_dummy_prediction(0),
        features=safe_features,
        main_factor="Mực nước ổn định ở mức an toàn",
    )
    assert alert_safe_2 is not None

    with db.connect() as conn:
        row = conn.execute("SELECT * FROM alert_events WHERE id = ?", (alert_safe_2,)).fetchone()
        assert row is not None
        assert row["event_type"] == "recovery"
        assert row["risk_level"] == 0
        assert "TRẠNG THÁI ĐÃ AN TOÀN" in row["message"]


