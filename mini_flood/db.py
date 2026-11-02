from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from .notification_settings import load_notification_config


SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    boot_id TEXT NOT NULL DEFAULT 'legacy',
    sequence_no INTEGER NOT NULL,
    experiment_id TEXT NOT NULL DEFAULT 'unassigned',
    scenario TEXT,
    schema_version INTEGER NOT NULL DEFAULT 1,
    timestamp TEXT NOT NULL,
    server_timestamp TEXT NOT NULL,
    rain_interval_mm REAL NOT NULL,
    rain_rate_mmh REAL NOT NULL,
    water_level_cm REAL NOT NULL,
    quality_flags TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    sample_interval_ms INTEGER,
    sample_age_ms INTEGER NOT NULL DEFAULT 0,
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
    inference_status TEXT NOT NULL DEFAULT 'warming_up',
    inference_mode TEXT NOT NULL DEFAULT 'model',
    forecasts_json TEXT NOT NULL DEFAULT '{}',
    upper_bounds_json TEXT NOT NULL DEFAULT '{}',
    ood INTEGER NOT NULL DEFAULT 0,
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
CREATE TABLE IF NOT EXISTS inference_runs (
    telemetry_id INTEGER PRIMARY KEY REFERENCES telemetry(id),
    trace_json TEXT NOT NULL,
    created_at TEXT NOT NULL
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
        self._transactions = threading.local()
        self.delivery_config = load_notification_config()
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
                    scenario TEXT,
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    timestamp TEXT NOT NULL,
                    server_timestamp TEXT NOT NULL,
                    rain_interval_mm REAL NOT NULL,
                    rain_rate_mmh REAL NOT NULL,
                    water_level_cm REAL NOT NULL,
                    quality_flags TEXT NOT NULL,
                    quality_status TEXT NOT NULL,
                    sample_interval_ms INTEGER,
                    sample_age_ms INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(device_id, boot_id, sequence_no)
                );
                INSERT INTO telemetry_boot_migration (
                    id, device_id, boot_id, sequence_no, experiment_id, scenario, schema_version,
                    timestamp, server_timestamp, rain_interval_mm,
                    rain_rate_mmh, water_level_cm, quality_flags, quality_status,
                    sample_interval_ms, sample_age_ms
                )
                SELECT
                    id, device_id, 'legacy', sequence_no, experiment_id, NULL, 1,
                    timestamp, server_timestamp, rain_interval_mm,
                    rain_rate_mmh, water_level_cm, quality_flags, quality_status,
                    NULL, 0
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

    def _migrate_v3_columns(self) -> None:
        with sqlite3.connect(self.path, timeout=10) as conn:
            telemetry_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(telemetry)").fetchall()
            }
            telemetry_additions = {
                "scenario": "TEXT",
                "schema_version": "INTEGER NOT NULL DEFAULT 1",
                "sample_interval_ms": "INTEGER",
                "sample_age_ms": "INTEGER NOT NULL DEFAULT 0",
            }
            for name, definition in telemetry_additions.items():
                if name not in telemetry_columns:
                    conn.execute(f"ALTER TABLE telemetry ADD COLUMN {name} {definition}")

            forecast_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(forecasts)").fetchall()
            }
            forecast_additions = {
                "horizon_unit": "TEXT NOT NULL DEFAULT 'minutes'",
                "inference_status": "TEXT NOT NULL DEFAULT 'warming_up'",
                "inference_mode": "TEXT NOT NULL DEFAULT 'legacy'",
                "forecasts_json": "TEXT NOT NULL DEFAULT '{}'",
                "upper_bounds_json": "TEXT NOT NULL DEFAULT '{}'",
                "ood": "INTEGER NOT NULL DEFAULT 0",
            }
            for name, definition in forecast_additions.items():
                if name not in forecast_columns:
                    conn.execute(f"ALTER TABLE forecasts ADD COLUMN {name} {definition}")
            delivery_columns = {row[1] for row in conn.execute("PRAGMA table_info(delivery_attempts)")}
            for name in ("claim_token", "claimed_until"):
                if name not in delivery_columns:
                    conn.execute(f"ALTER TABLE delivery_attempts ADD COLUMN {name} TEXT")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        current = getattr(self._transactions, "connection", None)
        if current is not None:
            yield current
            return
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def atomic(self):
        """One ingestion is committed with all its state/trace, or rolled back for retry."""
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._transactions.connection = conn
            try:
                yield
            except BaseException:
                conn.rollback()
                raise
            finally:
                self._transactions.connection = None

    def initialize(self) -> None:
        self._migrate_telemetry_boot_id()
        with self.connect() as conn:
            conn.executescript(SCHEMA)
        self._migrate_v3_columns()
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
        scenario: str | None = None,
    ) -> tuple[int, bool]:
        now = utc_now().isoformat()
        with self.connect() as conn:
            try:
                cur = conn.execute(
                    """
                    INSERT INTO telemetry (
                        device_id, boot_id, sequence_no, experiment_id, scenario, schema_version,
                        timestamp, server_timestamp,
                        rain_interval_mm, rain_rate_mmh, water_level_cm,
                        quality_flags, quality_status, sample_interval_ms, sample_age_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["device_id"], payload.get("boot_id", "legacy"),
                        payload["sequence_no"], experiment_id, scenario,
                        payload.get("schema_version", 1), payload["timestamp"], payload.get("server_timestamp", now),
                        payload["rain_interval_mm"], payload["rain_rate_mmh"], payload["water_level_cm"],
                        json.dumps(payload.get("quality_flags", []), ensure_ascii=False), quality_status,
                        payload.get("sample_interval_ms"), payload.get("sample_age_ms", 0),
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

    def get_recent_telemetry(
        self, device_id: str, end_time: datetime, minutes: int = 65, boot_id: str | None = None
    ) -> list[dict[str, Any]]:
        start = end_time - timedelta(minutes=minutes)
        with self.connect() as conn:
            sql = """
                SELECT * FROM telemetry
                WHERE device_id = ? AND julianday(timestamp) BETWEEN julianday(?) AND julianday(?)
            """
            params: list[Any] = [device_id, start.isoformat(), end_time.isoformat()]
            if boot_id is not None:
                sql += " AND boot_id = ?"
                params.append(boot_id)
            sql += " ORDER BY julianday(timestamp) ASC, sequence_no ASC"
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def save_forecast(
        self,
        telemetry_id: int,
        model_version: str,
        features: dict[str, float],
        forecasts: dict[int, float | None],
        alert_level: int,
        main_factor: str,
        safety_override: bool,
        inference_status: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO forecasts (
                    telemetry_id, model_version, features_json,
                    forecast_15m_cm, forecast_30m_cm, alert_level,
                    main_factor, safety_override, inference_status, inference_mode,
                    forecasts_json, upper_bounds_json, ood, created_at, horizon_unit
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'seconds')
                """,
                (
                    telemetry_id,
                    model_version,
                    json.dumps(features, ensure_ascii=False),
                    forecasts.get(15 * 60),
                    None,
                    alert_level,
                    main_factor,
                    int(safety_override),
                    inference_status,
                    "model",
                    json.dumps({str(k): v for k, v in forecasts.items()}),
                    json.dumps({str(k): None for k in forecasts}),
                    0,
                    utc_now().isoformat(),
                ),
            )

    @staticmethod
    def _inference(item: dict[str, Any]) -> dict[str, Any] | None:
        if item.get("model_version") is None:
            return None
        try:
            forecasts = json.loads(item.get("forecasts_json") or "{}")
            upper_bounds = json.loads(item.get("upper_bounds_json") or "{}")
        except (json.JSONDecodeError, TypeError):
            forecasts, upper_bounds = {}, {}
        return {
            "status": item.get("inference_status", "warming_up"),
            "mode": item.get("inference_mode", "legacy"),
            "model_version": item.get("model_version"),
            "forecasts": [
                {
                    "horizon_seconds": int(horizon) * (60 if item.get("horizon_unit", "minutes") == "minutes" else 1),
                    "horizon_minutes": (int(horizon) if item.get("horizon_unit", "minutes") == "minutes" else
                                        int(horizon) / 60 if int(horizon) % 60 == 0 else None),
                    "level_cm": value,
                    "upper_p90_cm": upper_bounds.get(str(horizon)),
                }
                for horizon, value in sorted(forecasts.items(), key=lambda pair: int(pair[0]))
            ],
            "ood": bool(item.get("ood", 0)),
        }

    def latest(self, device_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT t.*, f.model_version, f.features_json,
                       f.forecast_15m_cm, f.forecast_30m_cm, f.alert_level,
                       f.main_factor, f.safety_override, f.inference_status,
                       f.inference_mode, f.forecasts_json, f.upper_bounds_json, f.ood, f.horizon_unit,
                       c.overflow_level_cm, c.warning_margin_cm, c.hysteresis_cm,
                       c.recovery_hold_seconds,
                       (c.overflow_level_cm - c.warning_margin_cm) AS warning_level_cm
                FROM telemetry t
                LEFT JOIN forecasts f ON f.telemetry_id = t.id
                LEFT JOIN station_configs c ON c.device_id = t.device_id
                WHERE t.device_id = ? ORDER BY julianday(t.timestamp) DESC, t.id DESC LIMIT 1
                """,
                (device_id,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        if isinstance(item.get("quality_flags"), str):
            item["quality_flags"] = json.loads(item["quality_flags"])
        level = item.get("alert_level")
        item["alert_label"] = {0: "An toàn", 1: "Cảnh báo", 2: "Nguy hiểm"}.get(level)
        if item.get("safety_override") is not None:
            item["safety_override"] = bool(item["safety_override"])
        item["inference"] = self._inference(item)
        if item.get("features_json"):
            item["features"] = json.loads(item.pop("features_json"))
        item.pop("forecasts_json", None)
        item.pop("upper_bounds_json", None)
        self._attach_trace(item)
        return item

    def history(self, device_id: str, limit: int = 500) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT t.*, f.model_version, f.forecast_15m_cm, f.forecast_30m_cm,
                       f.alert_level, f.main_factor, f.safety_override,
                       f.inference_status, f.inference_mode, f.forecasts_json,
                       f.upper_bounds_json, f.ood, f.horizon_unit,
                       c.overflow_level_cm,
                       (c.overflow_level_cm - c.warning_margin_cm) AS warning_level_cm
                FROM telemetry t
                LEFT JOIN forecasts f ON f.telemetry_id = t.id
                LEFT JOIN station_configs c ON c.device_id = t.device_id
                WHERE t.device_id = ? ORDER BY julianday(t.timestamp) DESC, t.id DESC LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            if isinstance(item.get("quality_flags"), str):
                item["quality_flags"] = json.loads(item["quality_flags"])
            item["alert_label"] = {0: "An toàn", 1: "Cảnh báo", 2: "Nguy hiểm"}.get(
                item.get("alert_level")
            )
            if item.get("safety_override") is not None:
                item["safety_override"] = bool(item["safety_override"])
            item["inference"] = self._inference(item)
            item.pop("forecasts_json", None)
            item.pop("upper_bounds_json", None)
            self._attach_trace(item)
            output.append(item)
        return output

    def get_state(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute("SELECT value_json FROM system_state WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value_json"]) if row else default

    def save_inference_trace(self, telemetry_id: int, trace: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO inference_runs(telemetry_id, trace_json, created_at) VALUES (?, ?, ?)",
                (telemetry_id, json.dumps(trace, ensure_ascii=False, allow_nan=False), utc_now().isoformat()),
            )

    def _attach_trace(self, item: dict[str, Any]) -> None:
        with self.connect() as conn:
            row = conn.execute("SELECT trace_json FROM inference_runs WHERE telemetry_id = ?", (item["id"],)).fetchone()
        if row is not None:
            trace = json.loads(row["trace_json"])
            item["inference"] = trace["inference"]
            item["alert_level"] = trace["alert_level"]
            item["alert_label"] = {0: "An toàn", 1: "Cảnh báo", 2: "Nguy hiểm"}.get(item["alert_level"])
            item["alert_source"] = trace["alert_source"]
            item["device_timestamp"] = trace["raw_payload"].get("timestamp")
            item["timestamp_source"] = trace["timestamp_source"]
            item["inference_trace"] = trace

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

    def claim_delivery(self) -> dict[str, Any] | None:
        now = utc_now()
        stamp = now.isoformat()
        cutoff = (now - timedelta(seconds=self.delivery_config.message_ttl_seconds)).isoformat()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""UPDATE delivery_attempts SET status='retry', claim_token=NULL, claimed_until=NULL
                WHERE status='sending' AND claimed_until <= ?""", (stamp,))
            conn.execute("""UPDATE delivery_attempts SET status='expired'
                WHERE status IN ('pending','retry') AND alert_event_id IN (
                    SELECT a.id FROM alert_events a WHERE a.event_type IN ('escalation','recovery','reminder','sensor_overflow')
                    AND (a.created_at < ? OR EXISTS (
                        SELECT 1 FROM alert_events b WHERE b.device_id=a.device_id AND b.id>a.id
                        AND b.event_type IN ('escalation','recovery','reminder','sensor_overflow'))))""", (cutoff,))
            row = conn.execute("""SELECT d.*, a.message FROM delivery_attempts d
                JOIN alert_events a ON a.id=d.alert_event_id
                WHERE d.status IN ('pending','retry') AND d.next_attempt_at <= ?
                ORDER BY CASE d.channel WHEN 'telegram' THEN 0 ELSE 1 END, d.id LIMIT 1""", (stamp,)).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            until = (now + timedelta(seconds=self.delivery_config.claim_seconds)).isoformat()
            conn.execute("UPDATE delivery_attempts SET status='sending', claim_token=?, claimed_until=? WHERE id=?",
                         (token, until, row["id"]))
            return {**dict(row), "claim_token": token}

    def disable_delivery(self, delivery_id: int, claim_token: str):
        with self.connect() as conn:
            conn.execute("UPDATE delivery_attempts SET status='disabled', last_error='channel_not_configured' WHERE id=? AND claim_token=?",
                         (delivery_id, claim_token))

    def update_delivery(self, delivery_id: int, ok: bool, error: str = "", claim_token: str | None = None) -> None:
        delays = self.delivery_config.retry_seconds
        now = utc_now()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT attempt_count, claim_token FROM delivery_attempts WHERE id = ?", (delivery_id,)
            ).fetchone()
            if row is None:
                return
            if claim_token is not None and row["claim_token"] != claim_token:
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
                next_at = now + timedelta(seconds=delays[attempt_count - 1])
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

    def station_last_seen(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT c.device_id, MAX(t.server_timestamp) AS last_seen_at
                FROM station_configs c
                LEFT JOIN telemetry t ON t.device_id = c.device_id
                GROUP BY c.device_id
                ORDER BY last_seen_at IS NULL, last_seen_at DESC, c.device_id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def delivery_latency(self) -> dict[str, float | int | None]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT a.created_at, d.sent_at, d.channel, t.timestamp AS measurement_timestamp, t.quality_flags
                FROM delivery_attempts d
                JOIN alert_events a ON a.id = d.alert_event_id
                LEFT JOIN telemetry t ON t.id = a.telemetry_id
                WHERE d.status = 'sent' AND d.sent_at IS NOT NULL
                """
            ).fetchall()
        values = sorted(
            max(0.0, (datetime.fromisoformat(row["sent_at"]) - datetime.fromisoformat(row["created_at"])).total_seconds())
            for row in rows
        )
        if not values:
            return {"sent_count": 0, "p95_seconds": None}
        index = max(0, int(len(values) * 0.95 + 0.999999) - 1)
        channels = {}
        for channel in {row["channel"] for row in rows}:
            observed = sorted(max(0, (datetime.fromisoformat(row["sent_at"]) - datetime.fromisoformat(row["measurement_timestamp"])).total_seconds())
                              for row in rows if row["channel"] == channel and row["measurement_timestamp"]
                              and "clock_invalid" not in row["quality_flags"])
            channels[channel] = {"measured_sent_count": len(observed),
                "measurement_to_provider_p95_seconds": round(observed[max(0, __import__('math').ceil(len(observed) * .95) - 1)], 3) if observed else None}
        return {"sent_count": len(values), "p95_seconds": round(values[index], 3), "channels": channels}

    def experiment_rows(self, device_id: str | None = None) -> list[dict[str, Any]]:
        sql = """
            SELECT experiment_id, scenario, device_id, boot_id, sequence_no, server_timestamp,
                   schema_version, timestamp, sample_interval_ms, sample_age_ms,
                   rain_interval_mm, rain_rate_mmh, water_level_cm,
                   quality_flags, quality_status
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
