from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any

from .ai_settings import FEATURE_NAMES
from .broadcaster import TelemetryBroadcaster
from .config import MiniFloodSettings
from .db import MiniFloodDatabase, utc_now
from .features import build_features, identify_main_factor, sensor_validity
from .models import ALERT_LABELS, MiniFloodModelRegistry
from .notifications import AlertManager, DeliveryWorker
from .schemas import TelemetryPayload


class StationNotConfiguredError(ValueError):
    pass


class MiniFloodService:
    def __init__(self, settings: MiniFloodSettings):
        self.settings = settings
        self.config = settings.ai
        self.db = MiniFloodDatabase(settings.database_path, default_station={
            "device_id": settings.default_device_id,
            "overflow_level_cm": settings.default_overflow_level_cm,
            "warning_margin_cm": settings.default_warning_margin_cm,
            "hysteresis_cm": settings.default_hysteresis_cm,
            "recovery_hold_seconds": settings.default_recovery_hold_seconds,
        })
        self.registry = MiniFloodModelRegistry(settings)
        self.alerts = AlertManager(self.db, settings)
        self.alerts.model_version = self.registry.version
        self.delivery_worker = DeliveryWorker(self.db, settings=settings)
        self.broadcaster = TelemetryBroadcaster(settings.notifications.stream_queue_size)
        self._ingest_lock = threading.RLock()

    def ingest(self, payload: TelemetryPayload) -> dict[str, Any]:
        with self._ingest_lock:
            self._pending_event = None
            with self.db.atomic():
                result = self._ingest(payload)
            if self._pending_event is not None:
                self.broadcaster.publish_sync(self._pending_event)
            return result

    def _ingest(self, payload: TelemetryPayload) -> dict[str, Any]:
        started = perf_counter()
        station = self.db.get_station_config(payload.device_id)
        if station is None:
            raise StationNotConfiguredError(f"Thiết bị {payload.device_id} chưa có cấu hình trạm")
        received = utc_now()
        raw = payload.model_dump(mode="json")
        item = dict(raw)
        flags = list(payload.quality_flags)
        measured = payload.timestamp.astimezone(timezone.utc) if payload.timestamp else None
        timestamp_source = "device"
        if measured is None or measured < self.config.data.clock_min_timestamp:
            flags.append("clock_invalid")
            measured = received
            timestamp_source = "server"
        elif measured > received + timedelta(seconds=self.config.data.future_tolerance_seconds):
            flags.extend(["clock_invalid", "timestamp_in_future"])
            measured = received
            timestamp_source = "server"
        elif measured < received - timedelta(seconds=self.config.data.live_max_age_seconds):
            flags.append("stale_timestamp")
        last_live = self.db.get_state(f"last_live:{payload.device_id}", None)
        if last_live is not None and measured <= datetime.fromisoformat(last_live["timestamp"]):
            flags.append("out_of_order")
        item.update(timestamp=measured.isoformat(), server_timestamp=received.isoformat(),
                    quality_flags=list(dict.fromkeys(flags)))
        water_valid, rain_valid = sensor_validity(item)
        fresh = not ({"clock_invalid", "stale_timestamp", "timestamp_in_future", "out_of_order"} & set(flags))
        quality = "valid" if fresh and water_valid and rain_valid else "stale" if "stale_timestamp" in flags else "invalid"
        item["quality_status"] = quality
        experiment = self.db.get_state(f"active_experiment:{payload.device_id}", {"experiment_id": "unassigned", "scenario": None})
        telemetry_id, duplicate = self.db.insert_telemetry(
            item, quality, experiment["experiment_id"], experiment.get("scenario"))
        if duplicate:
            return self._ack(quality, True)
        if fresh:
            self.db.set_state(f"last_live:{payload.device_id}", {"timestamp": measured.isoformat()})
            self.alerts.evaluate_sensor_health(telemetry_id, payload.device_id, measured.isoformat(),
                                               water_valid, rain_valid, item["quality_flags"])

        state_key = f"alert_state:{payload.device_id}"
        previous = self.db.get_state(state_key, {})
        level = previous.get("alert_level")
        source = previous.get("alert_source")
        sensor_override = fresh and water_valid and payload.water_level_cm >= station["overflow_level_cm"]
        overflow_key = f"water_overflow:{payload.device_id}"
        was_overflowing = self.db.get_state(overflow_key, False)
        if fresh and water_valid:
            if sensor_override:
                self.db.set_state(overflow_key, True)
            elif payload.water_level_cm < station["overflow_level_cm"] - station["hysteresis_cm"]:
                self.db.set_state(overflow_key, False)
        factor = "Chưa có đánh giá AI"
        if sensor_override:
            factor = "Mực nước hiện tại đã vượt mức tràn"
            source = "sensor_rule"
            level, _ = self.alerts.evaluate(
                telemetry_id, payload.device_id, measured.isoformat(),
                {}, {"water_level_cm": payload.water_level_cm},
                station, factor, alert_source=source, sensor_entering=not was_overflowing)
        feature_started = perf_counter()
        features = None
        if not fresh or not water_valid or not rain_valid:
            reason = ", ".join(item["quality_flags"]) or "sensor_invalid"
            inference = self.registry.empty_result("invalid_input", reason)
        else:
            window = max(self.config.data.rain_window_seconds, self.config.data.rise_window_seconds)
            rows = self.db.get_recent_telemetry(payload.device_id, measured,
                                               minutes=(window + self.config.data.max_gap_seconds) / 60,
                                               boot_id=payload.boot_id)
            features, status = build_features(rows, self.config)
            inference = (self.registry.predict_detailed(features, measured) if features is not None else
                         self.registry.empty_result(status, "history_incomplete" if status == "warming_up" else "history_invalid"))
        inference["feature_and_predict_ms"] = (perf_counter() - feature_started) * 1000
        for entry in inference["forecasts"]:
            if entry["target_timestamp"] is None:
                entry["target_timestamp"] = (measured + timedelta(seconds=entry["horizon_seconds"])).isoformat()
        forecasts = {entry["horizon_seconds"]: entry["level_cm"] for entry in inference["forecasts"]}
        available = [value for value in forecasts.values() if value is not None]
        partial_level = (2 if available and max(available) >= station["overflow_level_cm"] else
                         1 if available and max(available) >= station["warning_level_cm"] else 0)
        if not sensor_override and fresh and (inference["status"] == "ready" or
                        (available and partial_level > (level if level is not None else 0))):
            factor = identify_main_factor(features, self.config)
            source = "model"
            level, _ = self.alerts.evaluate(
                telemetry_id, payload.device_id, measured.isoformat(), forecasts, features,
                station, factor, alert_source=source)
        elif not sensor_override:
            factor = "Chưa có kết quả AI hợp lệ: " + inference["status"]
            # Interrupt recovery holds when no valid prediction exists.
            if fresh and previous:
                previous.update(recovery_started_at=None, recovery_from_level=None)
                self.db.set_state(state_key, previous)

        inference["ingest_ms"] = (perf_counter() - started) * 1000
        trace = {
            "telemetry_id": telemetry_id, "raw_payload": raw,
            "measurement_timestamp": measured.isoformat(), "received_timestamp": received.isoformat(),
            "timestamp_source": timestamp_source, "quality_flags": item["quality_flags"],
            "feature_names": list(FEATURE_NAMES),
            "feature_vector": [features[name] for name in FEATURE_NAMES] if features else None,
            "features": features, "config_hash": self.config.config_hash,
            "config": self.config.model_dump(mode="json"),
            "feature_signature": self.config.feature_signature, "inference": inference,
            "alert_level": level, "alert_source": source, "station_config": station,
            "safety_override": bool(sensor_override), "reason": factor,
        }
        # Legacy alert column is NOT NULL; -1 represents unknown in that compatibility table.
        self.db.save_forecast(
            telemetry_id, self.registry.version, features or {}, forecasts,
            level if level is not None else -1,
            factor, bool(sensor_override), inference["status"])
        self.db.save_inference_trace(telemetry_id, trace)
        event = {
            "type": "telemetry", "telemetry_id": telemetry_id, "device_id": payload.device_id,
            "boot_id": payload.boot_id, "sequence_no": payload.sequence_no,
            "experiment_id": experiment["experiment_id"], "scenario": experiment.get("scenario"),
            "timestamp": measured.isoformat(), "server_timestamp": received.isoformat(),
            "device_timestamp": raw["timestamp"], "timestamp_source": timestamp_source,
            "water_level_cm": payload.water_level_cm, "rain_rate_mmh": payload.rain_rate_mmh,
            "rain_interval_mm": payload.rain_interval_mm, "quality_status": quality,
            "quality_flags": item["quality_flags"], "features": features, "inference": inference,
            "forecast_15m_cm": forecasts.get(15 * 60), "forecast_30m_cm": None,
            "alert_level": level, "alert_label": ALERT_LABELS.get(level), "alert_source": source,
            "main_factor": factor, "safety_override": bool(sensor_override), "is_live": fresh,
            "water_valid": water_valid, "rain_valid": rain_valid,
            "warning_level_cm": station["warning_level_cm"], "overflow_level_cm": station["overflow_level_cm"],
        }
        self._pending_event = event
        snapshot = self.db.get_state(f"snapshot:{payload.device_id}", {})
        snapshot["last_received"] = event
        snapshot["alert_state"] = self.db.get_state(state_key, {})
        if fresh:
            snapshot["current_inference"] = event
        if fresh and water_valid:
            snapshot["current_measurement"] = event
        if inference["status"] == "ready":
            snapshot["last_successful_inference"] = event
        self.db.set_state(f"snapshot:{payload.device_id}", snapshot)
        return self._ack(quality, False)

    @staticmethod
    def _ack(status: str, duplicate: bool) -> dict[str, Any]:
        return {"accepted": True, "duplicate": duplicate, "quality_status": status, "server_timestamp": utc_now()}

    def snapshot(self, device_id: str) -> dict[str, Any]:
        snapshot = self.db.get_state(f"snapshot:{device_id}", {})
        now = utc_now()
        for name in ("last_received", "current_measurement", "current_inference", "last_successful_inference"):
            item = snapshot.get(name)
            if item:
                age = (now - datetime.fromisoformat(item["timestamp"])).total_seconds()
                item["age_seconds"] = max(0, age)
                item["received_age_seconds"] = max(0, (now - datetime.fromisoformat(item["server_timestamp"])).total_seconds())
                item["stale"] = age > self.config.data.live_max_age_seconds
        return {"device_id": device_id, "runtime_mode": self.settings.runtime_mode,
                "data_source": self.registry.data_source, "model_ready": self.registry.ready,
                "server_timestamp": now.isoformat(),
                "dashboard_refresh_seconds": self.settings.notifications.dashboard_refresh_seconds, **snapshot}
