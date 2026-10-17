import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from mini_flood.config import MiniFloodSettings
from mini_flood.db import MiniFloodDatabase
from mini_flood_api import create_app


def build_test_client(tmp_path: Path):
    db_path = tmp_path / "offline_buffer.sqlite3"
    settings = MiniFloodSettings(
        database_path=db_path,
        model_dir=tmp_path / "models",
        device_api_key="buffer-test-key",
        notification_worker_enabled=False,
    )
    app = create_app(settings)
    client = TestClient(app)
    db = MiniFloodDatabase(db_path)
    return client, db


def make_payload(seq: int, stamp: datetime, water: float = 12.0, rain: float = 10.0):
    return {
        "schema_version": 1,
        "device_id": "mini-flood-station-01",
        "sequence_no": seq,
        "timestamp": stamp.isoformat(),
        "rain_interval_mm": rain / 60.0,
        "rain_rate_mmh": rain,
        "water_level_cm": water,
        "quality_flags": [],
    }


def test_buffered_payloads_accepted(tmp_path):
    """Kiểm tra kịch bản ESP32 mất Wi-Fi, lưu đệm 5 bản ghi vào queue,
    và gửi dồn dập (flush) lên server ngay khi kết nối lại.
    Server phải lưu đúng thứ tự, chống trùng lặp và phản hồi HTTP 200.
    """
    client, db = build_test_client(tmp_path)
    headers = {"X-Device-Key": "buffer-test-key"}

    # Giả lập thời gian đo đạc trong 5 phút vừa qua (mỗi phút 1 bản ghi)
    end = datetime.now(timezone.utc)
    buffered_records = [
        make_payload(seq=i + 1, stamp=end - timedelta(minutes=5 - i), water=10.0 + i)
        for i in range(5)
    ]

    # ESP32 reconnect và đẩy 5 bản ghi đệm
    for record in buffered_records:
        res = client.post("/api/v1/telemetry", json=record, headers=headers)
        assert res.status_code == 200
        assert res.json()["accepted"] is True
        assert res.json()["duplicate"] is False

    # Giả lập bản ghi seq=3 bị gửi lại lần 2 do mất ACK từ server
    res_dup = client.post("/api/v1/telemetry", json=buffered_records[2], headers=headers)
    assert res_dup.status_code == 200
    assert res_dup.json()["accepted"] is True
    assert res_dup.json()["duplicate"] is True

    # Kiểm tra database: chỉ có đúng 5 bản ghi telemetry duy nhất
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT sequence_no, water_level_cm FROM telemetry WHERE device_id = 'mini-flood-station-01' ORDER BY sequence_no ASC"
        ).fetchall()
        assert len(rows) == 5
        seqs = [r["sequence_no"] for r in rows]
        assert seqs == [1, 2, 3, 4, 5]


def test_stale_timestamp_flagged(tmp_path):
    """Kiểm tra xử lý bản ghi đến quá muộn (stale timestamp > 10 phút):
    - Server vẫn lưu trữ bản ghi vào DB để phục vụ kiểm tra/lịch sử.
    - Đánh dấu quality_flags chứa 'stale_timestamp', quality_status='unknown'.
    - Không chạy dự báo AI với bản ghi bị trễ này.
    """
    client, db = build_test_client(tmp_path)
    headers = {"X-Device-Key": "buffer-test-key"}

    stale_time = datetime.now(timezone.utc) - timedelta(minutes=25)
    payload = make_payload(seq=99, stamp=stale_time, water=14.0, rain=20.0)

    res = client.post("/api/v1/telemetry", json=payload, headers=headers)
    assert res.status_code == 200

    data = res.json()
    assert data["accepted"] is True
    assert data["quality_status"] == "unknown"
    assert data["predictions"] is None

    # Kiểm tra bản ghi lưu trong database có flag stale_timestamp
    with db.connect() as conn:
        row = conn.execute(
            "SELECT quality_flags, quality_status FROM telemetry WHERE sequence_no = 99"
        ).fetchone()
        assert row is not None
        assert row["quality_status"] == "unknown"
        assert "stale_timestamp" in row["quality_flags"]

