import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from mini_flood.config import MiniFloodSettings
from mini_flood.db import MiniFloodDatabase
from mini_flood_api import create_app


def build_test_client(tmp_path: Path):
    db_path = tmp_path / "e2e_mini.sqlite3"
    settings = MiniFloodSettings(
        database_path=db_path,
        model_dir=tmp_path / "models",
        device_api_key="iot-test-key",
        notification_worker_enabled=False,
    )
    app = create_app(settings)
    client = TestClient(app)
    db = MiniFloodDatabase(db_path)
    return client, db, settings


def make_payload(seq: int, stamp: datetime, water: float, rain: float, dev_id: str = "mini-flood-station-01"):
    return {
        "schema_version": 1,
        "device_id": dev_id,
        "sequence_no": seq,
        "timestamp": stamp.isoformat(),
        "rain_interval_mm": rain / 60.0,
        "rain_rate_mmh": rain,
        "water_level_cm": water,
        "quality_flags": [],
    }


def test_scenario_normal(tmp_path):
    """Kịch bản Bình thường: Mực nước thấp, mưa nhỏ, chạy 20 phút.
    Sau giai đoạn warming-up, AI dự báo An toàn (Mức 0) và không kích hoạt alert.
    """
    client, db, _ = build_test_client(tmp_path)
    headers = {"X-Device-Key": "iot-test-key"}

    end = datetime.now(timezone.utc)
    responses = []

    for i in range(20):
        t = end - timedelta(minutes=19 - i)
        payload = make_payload(seq=i + 1, stamp=t, water=8.0, rain=2.0)
        res = client.post("/api/v2/telemetry", json=payload, headers=headers)
        assert res.status_code == 200
        responses.append(res.json())

    # Các bản ghi đầu đang thu thập lịch sử hoặc có cờ stale do thời gian quá khứ
    assert responses[0]["quality_status"] in {"unknown", "warming_up"}
    assert "predictions" not in responses[0]

    # Bản ghi cuối (thời điểm hiện tại) có dữ liệu hợp lệ và AI dự báo Mức 0
    last_res = responses[-1]
    assert last_res["quality_status"] == "valid"
    assert "predictions" not in last_res
    latest = db.latest("mini-flood-station-01")
    assert latest is not None
    assert latest["alert_level"] == 0
    assert latest["forecast_15m_cm"] == pytest.approx(8.0)
    assert latest["safety_override"] == 0

    # Xác nhận cơ sở dữ liệu không sinh bất kỳ cảnh báo nào
    with db.connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM alert_events").fetchone()["c"]
        assert count == 0


def test_scenario_warning(tmp_path):
    """Kịch bản Mưa lớn & Nước dâng: Chạy 20 phút, nửa sau xuất hiện mưa to và nước dâng nhanh.
    Hệ thống nâng mức rủi ro lên Cảnh báo (Mức 1 hoặc 2) và enqueue alert escalation.
    """
    client, db, _ = build_test_client(tmp_path)
    headers = {"X-Device-Key": "iot-test-key"}

    end = datetime.now(timezone.utc)
    responses = []

    for i in range(20):
        t = end - timedelta(minutes=19 - i)
        # 10 phút đầu bình thường, 10 phút sau mưa 45mm/h và nước dâng từ 10 lên 19cm
        if i < 10:
            water = 8.0
            rain = 5.0
        else:
            water = 10.0 + (i - 10) * 1.0  # lên đến 19.0 cm
            rain = 45.0
        payload = make_payload(seq=i + 1, stamp=t, water=water, rain=rain)
        res = client.post("/api/v2/telemetry", json=payload, headers=headers)
        assert res.status_code == 200
        responses.append(res.json())

    last_res = responses[-1]
    assert last_res["quality_status"] == "valid"
    assert "predictions" not in last_res
    latest = db.latest("mini-flood-station-01")
    assert latest is not None
    assert latest["alert_level"] >= 1
    assert latest["forecast_15m_cm"] is not None
    assert latest["main_factor"] is not None

    # Kiểm tra database: AlertManager phải enqueue một sự kiện escalation
    with db.connect() as conn:
        alerts = conn.execute(
            "SELECT * FROM alert_events WHERE event_type = 'escalation' ORDER BY id ASC"
        ).fetchall()
        assert len(alerts) >= 1
        first_alert = dict(alerts[0])
        assert first_alert["alert_level"] >= 1
        assert "CẢNH BÁO NGUY CƠ NGẬP" in first_alert["message"]

        # Kiểm tra bảng delivery_attempts: background worker tự động xử lý khi nhận telemetry
        deliveries = conn.execute(
            "SELECT channel, status FROM delivery_attempts WHERE alert_event_id = ?",
            (first_alert["id"],),
        ).fetchall()
        channels = {row["channel"] for row in deliveries}
        assert "telegram" in channels
        assert "email" in channels
        assert all(row["status"] in {"pending", "retry", "sent"} for row in deliveries)


def test_scenario_danger(tmp_path):
    """Kịch bản Ngập nguy hiểm: Mực nước đo được vượt ngưỡng nguy hiểm (30 cm >= 25 cm).
    Hệ thống kích hoạt ngay Safety Rule Override lên Mức 2 và enqueue cảnh báo khẩn cấp
    ngay từ bản ghi đầu tiên mà không cần chờ đủ 15 phút warming-up.
    """
    client, db, _ = build_test_client(tmp_path)
    headers = {"X-Device-Key": "iot-test-key"}

    now = datetime.now(timezone.utc)
    payload = make_payload(seq=1, stamp=now, water=42.0, rain=60.0)
    res = client.post("/api/v2/telemetry", json=payload, headers=headers)
    assert res.status_code == 200

    data = res.json()
    assert data["accepted"] is True
    assert "predictions" not in data
    latest = db.latest("mini-flood-station-01")
    assert latest is not None
    assert latest["safety_override"] == 1
    assert latest["alert_level"] == 2
    assert "vượt ngưỡng nguy hiểm" in latest["main_factor"]

    # Kiểm tra database: AlertManager phải enqueue ngay một sự kiện escalation Mức 2
    with db.connect() as conn:
        alerts = conn.execute("SELECT * FROM alert_events WHERE alert_level = 2").fetchall()
        assert len(alerts) == 1
        alert = dict(alerts[0])
        assert alert["event_type"] == "escalation"
        assert "CẢNH BÁO NGUY CƠ NGẬP" in alert["message"]

        # Kiểm tra delivery attempts
        deliveries = conn.execute(
            "SELECT channel, status FROM delivery_attempts WHERE alert_event_id = ?",
            (alert["id"],),
        ).fetchall()
        assert len(deliveries) == 2
        channels = {row["channel"] for row in deliveries}
        assert channels == {"telegram", "email"}



