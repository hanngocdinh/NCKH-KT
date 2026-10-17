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
CREATE INDEX IF NOT EXISTS idx_telemetry_device_time
    ON telemetry(device_id, timestamp);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telemetry_id INTEGER NOT NULL UNIQUE,
    model_version TEXT NOT NULL,
    features_json TEXT NOT NULL,
    risk_15m INTEGER,
    probs_15m TEXT,
    risk_30m INTEGER,
    probs_30m TEXT,
    main_factor TEXT,
    rule_override INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(telemetry_id) REFERENCES telemetry(id)
);

CREATE TABLE IF NOT EXISTS alert_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telemetry_id INTEGER,
    device_id TEXT NOT NULL,
    event_key TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    risk_level INTEGER NOT NULL,
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
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

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
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(telemetry)")}
            if "experiment_id" not in columns:
                conn.execute("ALTER TABLE telemetry ADD COLUMN experiment_id TEXT NOT NULL DEFAULT 'unassigned'")

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
                        device_id, sequence_no, experiment_id, timestamp, server_timestamp,
                        rain_interval_mm, rain_rate_mmh, water_level_cm,
                        quality_flags, quality_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["device_id"], payload["sequence_no"], experiment_id, payload["timestamp"], now,
                        payload["rain_interval_mm"], payload["rain_rate_mmh"], payload["water_level_cm"],
                        json.dumps(payload.get("quality_flags", []), ensure_ascii=False), quality_status,
                    ),
                )
                return int(cur.lastrowid), False
            except sqlite3.IntegrityError:
                row = conn.execute(
                    "SELECT id FROM telemetry WHERE device_id = ? AND sequence_no = ?",
                    (payload["device_id"], payload["sequence_no"]),
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

    def save_prediction(
        self,
        telemetry_id: int,
        model_version: str,
        features: dict[str, float],
        predictions: dict[str, dict[str, Any]],
        main_factor: str,
        rule_override: bool,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO predictions (
                    telemetry_id, model_version, features_json,
                    risk_15m, probs_15m, risk_30m, probs_30m,
                    main_factor, rule_override, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telemetry_id,
                    model_version,
                    json.dumps(features, ensure_ascii=False),
                    predictions["15m"]["risk_level"],
                    json.dumps(predictions["15m"]["probabilities"]),
                    predictions["30m"]["risk_level"],
                    json.dumps(predictions["30m"]["probabilities"]),
                    main_factor,
                    int(rule_override),
                    utc_now().isoformat(),
                ),
            )

    def get_prediction(self, telemetry_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM predictions WHERE telemetry_id = ?", (telemetry_id,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        return {
            "model_version": item["model_version"],
            "features": json.loads(item["features_json"]),
            "predictions": {
                "15m": {"risk_level": item["risk_15m"], "probabilities": json.loads(item["probs_15m"])},
                "30m": {"risk_level": item["risk_30m"], "probabilities": json.loads(item["probs_30m"])},
            },
            "main_factor": item["main_factor"],
            "rule_override": bool(item["rule_override"]),
        }

    def latest(self, device_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT t.*, p.model_version, p.features_json, p.risk_15m, p.probs_15m,
                       p.risk_30m, p.probs_30m, p.main_factor, p.rule_override
                FROM telemetry t LEFT JOIN predictions p ON p.telemetry_id = t.id
                WHERE t.device_id = ? ORDER BY t.timestamp DESC, t.sequence_no DESC LIMIT 1
                """,
                (device_id,),
            ).fetchone()
        return dict(row) if row else None

    def history(self, device_id: str, limit: int = 500) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT t.*, p.model_version, p.risk_15m, p.risk_30m, p.main_factor
                FROM telemetry t LEFT JOIN predictions p ON p.telemetry_id = t.id
                WHERE t.device_id = ? ORDER BY t.timestamp DESC, t.sequence_no DESC LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

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
        risk_level: int,
        message: str,
        channels: tuple[str, ...] = ("telegram", "email"),
    ) -> int | None:
        now = utc_now().isoformat()
        with self.connect() as conn:
            try:
                cur = conn.execute(
                    """INSERT INTO alert_events
                    (telemetry_id, device_id, event_key, event_type, risk_level, message, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (telemetry_id, device_id, event_key, event_type, risk_level, message, now),
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
