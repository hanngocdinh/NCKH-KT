import sqlite3

from mini_flood.db import MiniFloodDatabase


def test_old_v2_database_is_migrated_without_losing_telemetry(tmp_path):
    path = tmp_path / "old-v2.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                sequence_no INTEGER NOT NULL,
                experiment_id TEXT NOT NULL DEFAULT 'unassigned',
                timestamp TEXT NOT NULL,
                server_timestamp TEXT NOT NULL,
                rain_interval_mm REAL NOT NULL,
                rain_rate_mmh REAL NOT NULL,
                water_level_cm REAL NOT NULL,
                quality_flags TEXT NOT NULL,
                quality_status TEXT NOT NULL,
                UNIQUE(device_id, sequence_no)
            );
            INSERT INTO telemetry (
                device_id, sequence_no, timestamp, server_timestamp,
                rain_interval_mm, rain_rate_mmh, water_level_cm,
                quality_flags, quality_status
            ) VALUES (
                'mini-flood-station-01', 154,
                '2026-10-20T18:15:29+07:00', '2026-10-20T18:17:39+07:00',
                0, 0, 29.57, '[]', 'valid'
            );
            """
        )

    db = MiniFloodDatabase(path)
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM telemetry").fetchone()
        columns = {item[1] for item in conn.execute("PRAGMA table_info(telemetry)")}
        assert "boot_id" in columns
        assert row["boot_id"] == "legacy"
        assert row["sequence_no"] == 154

    new_id, duplicate = db.insert_telemetry(
        {
            "device_id": "mini-flood-station-01",
            "boot_id": "boot-after-restart",
            "sequence_no": 154,
            "timestamp": "2026-10-20T20:30:00+07:00",
            "rain_interval_mm": 0.1,
            "rain_rate_mmh": 10,
            "water_level_cm": 30,
            "quality_flags": [],
        },
        "valid",
    )
    assert new_id > 0
    assert duplicate is False
