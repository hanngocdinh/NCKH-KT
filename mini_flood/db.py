from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    boot_id TEXT NOT NULL DEFAULT 'legacy',
    sequence_no INTEGER NOT NULL,
    experiment_id TEXT NOT NULL DEFAULT 'unassigned',
    timestamp TEXT NOT NULL,
    server_timestamp TEXT NOT NULL,
    rain_interval_mm REAL NOT NULL,
    rain_rate_mmh REAL NOT NULL,
    water_level_cm REAL NOT NULL,
    quality_flags TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    UNIQUE(device_id, boot_id, sequence_no)
);
CREATE INDEX IF NOT EXISTS idx_telemetry_device_time
    ON telemetry(device_id, timestamp);

CREATE TABLE IF NOT EXISTS station_configs (
    device_id TEXT PRIMARY KEY,
    overflow_level_cm REAL NOT NULL,
    warning_margin_cm REAL NOT NULL,
    hysteresis_cm REAL NOT NULL,
    recovery_hold_seconds INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telemetry_id INTEGER NOT NULL UNIQUE,
    model_version TEXT NOT NULL,
    features_json TEXT NOT NULL,
    forecast_15m_cm REAL,
    forecast_30m_cm REAL,
    alert_level INTEGER NOT NULL,
    main_factor TEXT,
    safety_override INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(telemetry_id) REFERENCES telemetry(id)
);

CREATE TABLE IF NOT EXISTS alert_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telemetry_id INTEGER,
    device_id TEXT NOT NULL,
    event_key TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    alert_level INTEGER NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(telemetry_id) REFERENCES telemetry(id)
);

CREATE TABLE IF NOT EXISTS delivery_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_event_id INTEGER NOT NULL,
    channel TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    next_attempt_at TEXT NOT NULL,
    last_error TEXT,
    sent_at TEXT,
    UNIQUE(alert_event_id, channel),
    FOREIGN KEY(alert_event_id) REFERENCES alert_events(id)
);

CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MiniFloodDatabase:
    def __init__(
        self,
        path: Path | str,
        default_station: dict[str, Any] | None = None,
    ):
        self.path = Path(path)
        self.default_station = default_station
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _migrate_telemetry_boot_id(self) -> None:
        """Nâng DB V2 cũ mà không xóa lịch sử telemetry/forecast."""
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='telemetry'"
            ).fetchone()
            if table is None:
                return
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(telemetry)").fetchall()
            }
            if "boot_id" in columns:
                return

            conn.execute("PRAGMA foreign_keys = OFF")
            conn.executescript(
                """
                BEGIN IMMEDIATE;
                CREATE TABLE telemetry_boot_migration (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    boot_id TEXT NOT NULL DEFAULT 'legacy',
                    sequence_no INTEGER NOT NULL,
                    experiment_id TEXT NOT NULL DEFAULT 'unassigned',
                    timestamp TEXT NOT NULL,
                    server_timestamp TEXT NOT NULL,
                    rain_interval_mm REAL NOT NULL,
                    rain_rate_mmh REAL NOT NULL,
                    water_level_cm REAL NOT NULL,
                    quality_flags TEXT NOT NULL,
                    quality_status TEXT NOT NULL,
                    UNIQUE(device_id, boot_id, sequence_no)
                );
                INSERT INTO telemetry_boot_migration (
                    id, device_id, boot_id, sequence_no, experiment_id,
                    timestamp, server_timestamp, rain_interval_mm,
                    rain_rate_mmh, water_level_cm, quality_flags, quality_status
                )
                SELECT
                    id, device_id, 'legacy', sequence_no, experiment_id,
                    timestamp, server_timestamp, rain_interval_mm,
                    rain_rate_mmh, water_level_cm, quality_flags, quality_status
                FROM telemetry;
                DROP TABLE telemetry;
                ALTER TABLE telemetry_boot_migration RENAME TO telemetry;
                COMMIT;
                """
            )
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        self._migrate_telemetry_boot_id()
        with self.connect() as conn:
            conn.executescript(SCHEMA)
        if self.default_station:
            self.create_station_config_if_missing(**self.default_station)

    @staticmethod
    def _station_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["warning_level_cm"] = round(
            float(item["overflow_level_cm"]) - float(item["warning_margin_cm"]), 4
        )
        return item

    def create_station_config_if_missing(
        self,
        device_id: str,
        overflow_level_cm: float,
        warning_margin_cm: float,
        hysteresis_cm: float,
        recovery_hold_seconds: int,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO station_configs (
                    device_id, overflow_level_cm, warning_margin_cm,
                    hysteresis_cm, recovery_hold_seconds, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id, overflow_level_cm, warning_margin_cm,
                    hysteresis_cm, recovery_hold_seconds, utc_now().isoformat(),
                ),
            )

    def get_station_config(self, device_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM station_configs WHERE device_id = ?", (device_id,)
            ).fetchone()
        return self._station_row(row)

    def upsert_station_config(
        self,
        device_id: str,
        overflow_level_cm: float,
        warning_margin_cm: float,
        hysteresis_cm: float,
        recovery_hold_seconds: int,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO station_configs (
                    device_id, overflow_level_cm, warning_margin_cm,
                    hysteresis_cm, recovery_hold_seconds, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    overflow_level_cm=excluded.overflow_level_cm,
                    warning_margin_cm=excluded.warning_margin_cm,
                    hysteresis_cm=excluded.hysteresis_cm,
                    recovery_hold_seconds=excluded.recovery_hold_seconds,
                    updated_at=excluded.updated_at
                """,
                (
                    device_id, overflow_level_cm, warning_margin_cm,
                    hysteresis_cm, recovery_hold_seconds, utc_now().isoformat(),
                ),
            )
        item = self.get_station_config(device_id)
        assert item is not None
        return item

    def insert_telemetry(
        self,
        payload: dict[str, Any],
        quality_status: str,
        experiment_id: str = "unassigned",
    ) -> tuple[int, bool]:
        now = utc_now().isoformat()
        with self.connect() as conn:
            try:
                cur = conn.execute(
                    """
                    INSERT INTO telemetry (
                        device_id, boot_id, sequence_no, experiment_id, timestamp, server_timestamp,
                        rain_interval_mm, rain_rate_mmh, water_level_cm,
                        quality_flags, quality_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["device_id"], payload.get("boot_id", "legacy"),
                        payload["sequence_no"], experiment_id, payload["timestamp"], now,
                        payload["rain_interval_mm"], payload["rain_rate_mmh"], payload["water_level_cm"],
                        json.dumps(payload.get("quality_flags", []), ensure_ascii=False), quality_status,
                    ),
                )
                return int(cur.lastrowid), False
            except sqlite3.IntegrityError:
                row = conn.execute(
                    """SELECT id FROM telemetry
                       WHERE device_id = ? AND boot_id = ? AND sequence_no = ?""",
                    (
                        payload["device_id"], payload.get("boot_id", "legacy"),
                        payload["sequence_no"],
                    ),
                ).fetchone()
                if row is None:
                    raise
                return int(row["id"]), True

    def get_recent_telemetry(self, device_id: str, end_time: datetime, minutes: int = 65) -> list[dict[str, Any]]:
        start = end_time - timedelta(minutes=minutes)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM telemetry
                WHERE device_id = ? AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC, sequence_no ASC
                """,
                (device_id, start.isoformat(), end_time.isoformat()),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_forecast(
        self,
        telemetry_id: int,
        model_version: str,
        features: dict[str, float],
        forecast_15m_cm: float | None,
        forecast_30m_cm: float | None,
        alert_level: int,
        main_factor: str,
        safety_override: bool,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO forecasts (
                    telemetry_id, model_version, features_json,
                    forecast_15m_cm, forecast_30m_cm, alert_level,
                    main_factor, safety_override, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telemetry_id,
                    model_version,
                    json.dumps(features, ensure_ascii=False),
                    forecast_15m_cm,
                    forecast_30m_cm,
                    alert_level,
                    main_factor,
                    int(safety_override),
                    utc_now().isoformat(),
                ),
            )

    def get_forecast(self, telemetry_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM forecasts WHERE telemetry_id = ?", (telemetry_id,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["features"] = json.loads(item.pop("features_json"))
        item["safety_override"] = bool(item["safety_override"])
        return item

    def latest(self, device_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT t.*, f.model_version, f.features_json,
                       f.forecast_15m_cm, f.forecast_30m_cm, f.alert_level,
                       f.main_factor, f.safety_override,
                       c.overflow_level_cm, c.warning_margin_cm, c.hysteresis_cm,
                       c.recovery_hold_seconds,
                       (c.overflow_level_cm - c.warning_margin_cm) AS warning_level_cm
                FROM telemetry t
                LEFT JOIN forecasts f ON f.telemetry_id = t.id
                LEFT JOIN station_configs c ON c.device_id = t.device_id
                WHERE t.device_id = ? ORDER BY t.timestamp DESC, t.sequence_no DESC LIMIT 1
                """,
                (device_id,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        level = item.get("alert_level")
        item["alert_label"] = {0: "An toàn", 1: "Cảnh báo", 2: "Nguy hiểm"}.get(level)
        if item.get("safety_override") is not None:
            item["safety_override"] = bool(item["safety_override"])
        return item

    def history(self, device_id: str, limit: int = 500) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT t.*, f.model_version, f.forecast_15m_cm, f.forecast_30m_cm,
                       f.alert_level, f.main_factor, f.safety_override,
                       c.overflow_level_cm,
                       (c.overflow_level_cm - c.warning_margin_cm) AS warning_level_cm
                FROM telemetry t
                LEFT JOIN forecasts f ON f.telemetry_id = t.id
                LEFT JOIN station_configs c ON c.device_id = t.device_id
                WHERE t.device_id = ? ORDER BY t.timestamp DESC, t.sequence_no DESC LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["alert_label"] = {0: "An toàn", 1: "Cảnh báo", 2: "Nguy hiểm"}.get(
                item.get("alert_level")
            )
            if item.get("safety_override") is not None:
                item["safety_override"] = bool(item["safety_override"])
            output.append(item)
        return output

    def get_state(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute("SELECT value_json FROM system_state WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value_json"]) if row else default

    def set_state(self, key: str, value: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO system_state(key, value_json, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at
                """,
                (key, json.dumps(value, ensure_ascii=False), utc_now().isoformat()),
            )

    def enqueue_alert(
        self,
        telemetry_id: int | None,
        device_id: str,
        event_key: str,
        event_type: str,
        alert_level: int,
        message: str,
        channels: tuple[str, ...] = ("telegram", "email"),
    ) -> int | None:
        now = utc_now().isoformat()
        with self.connect() as conn:
            try:
                cur = conn.execute(
                    """INSERT INTO alert_events
                    (telemetry_id, device_id, event_key, event_type, alert_level, message, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (telemetry_id, device_id, event_key, event_type, alert_level, message, now),
                )
            except sqlite3.IntegrityError:
                existing = conn.execute(
                    "SELECT id FROM alert_events WHERE event_key = ?", (event_key,)
                ).fetchone()
                if existing is not None:
                    return None
                raise
            alert_id = int(cur.lastrowid)
            for channel in channels:
                conn.execute(
                    """INSERT INTO delivery_attempts
                    (alert_event_id, channel, attempt_count, status, next_attempt_at)
                    VALUES (?, ?, 0, 'pending', ?)""",
                    (alert_id, channel, now),
                )
            return alert_id

    def due_deliveries(self, limit: int = 20) -> list[dict[str, Any]]:
        now = utc_now().isoformat()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT d.*, a.message FROM delivery_attempts d
                JOIN alert_events a ON a.id = d.alert_event_id
                WHERE d.status IN ('pending', 'retry') AND d.next_attempt_at <= ?
                ORDER BY d.next_attempt_at ASC LIMIT ?
                """,
                (now, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_delivery(self, delivery_id: int, ok: bool, error: str = "") -> None:
        delays = (1, 5, 15, 30)
        now = utc_now()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT attempt_count FROM delivery_attempts WHERE id = ?", (delivery_id,)
            ).fetchone()
            if row is None:
                return
            attempt_count = int(row["attempt_count"]) + 1
            if ok:
                conn.execute(
                    """UPDATE delivery_attempts SET attempt_count=?, status='sent', sent_at=?, last_error=NULL
                    WHERE id=?""",
                    (attempt_count, now.isoformat(), delivery_id),
                )
                return
            if attempt_count > len(delays):
                status = "failed"
                next_at = now
            else:
                status = "retry"
                next_at = now + timedelta(minutes=delays[attempt_count - 1])
            conn.execute(
                """UPDATE delivery_attempts
                SET attempt_count=?, status=?, next_attempt_at=?, last_error=? WHERE id=?""",
                (attempt_count, status, next_at.isoformat(), error[:500], delivery_id),
            )

    def counts(self) -> dict[str, int]:
        with self.connect() as conn:
            telemetry = conn.execute("SELECT COUNT(*) AS n FROM telemetry").fetchone()["n"]
            pending = conn.execute(
                "SELECT COUNT(*) AS n FROM delivery_attempts WHERE status IN ('pending', 'retry')"
            ).fetchone()["n"]
        return {"telemetry": int(telemetry), "pending_deliveries": int(pending)}

    def experiment_rows(self, device_id: str | None = None) -> list[dict[str, Any]]:
        sql = """
            SELECT experiment_id, device_id, sequence_no, timestamp,
                   rain_interval_mm, rain_rate_mmh, water_level_cm, quality_flags
            FROM telemetry WHERE experiment_id <> 'unassigned'
        """
        params: tuple[Any, ...] = ()
        if device_id:
            sql += " AND device_id = ?"
            params = (device_id,)
        sql += " ORDER BY timestamp ASC, sequence_no ASC"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
