from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .broadcaster import broadcaster
from .config import MiniFloodSettings
from .db import MiniFloodDatabase, utc_now
from .features import build_features, identify_main_factor
from .models import ALERT_LABELS, MiniFloodModelRegistry
from .notifications import AlertManager, DeliveryWorker
from .schemas import TelemetryPayload


class StationNotConfiguredError(ValueError):
    pass


class MiniFloodService:
    def __init__(self, settings: MiniFloodSettings):
        self.settings = settings
        self.db = MiniFloodDatabase(
            settings.database_path,
            default_station={
                "device_id": settings.default_device_id,
                "overflow_level_cm": settings.default_overflow_level_cm,
                "warning_margin_cm": settings.default_warning_margin_cm,
                "hysteresis_cm": settings.default_hysteresis_cm,
                "recovery_hold_seconds": settings.default_recovery_hold_seconds,
            },
        )
        self.registry = MiniFloodModelRegistry(settings)
        self.alerts = AlertManager(self.db, settings)
        self.delivery_worker = DeliveryWorker(self.db)
        self.broadcaster = broadcaster

    @staticmethod
    def _timestamp_quality(timestamp: datetime) -> list[str]:
        now = datetime.now(timezone.utc)
        value = timestamp.astimezone(timezone.utc)
        flags: list[str] = []
        if value > now + timedelta(minutes=5):
            flags.append("timestamp_in_future")
        if value < now - timedelta(minutes=10):
            flags.append("stale_timestamp")
        return flags

    def ingest(self, payload: TelemetryPayload) -> dict[str, Any]:
        station = self.db.get_station_config(payload.device_id)
        if station is None:
            raise StationNotConfiguredError(
                f"Thiết bị {payload.device_id} chưa có cấu hình trạm"
            )
        item = payload.model_dump(mode="json")
        timestamp = payload.timestamp
        if timestamp.year < 2020:
            timestamp = utc_now()
            item["timestamp"] = timestamp.isoformat()
        quality_flags = list(payload.quality_flags)
        quality_flags.extend(flag for flag in self._timestamp_quality(timestamp) if flag not in quality_flags)
        item["quality_flags"] = quality_flags
        quality_status = "valid" if not quality_flags else "unknown"

        experiment = self.db.get_state(
            f"active_experiment:{payload.device_id}",
            {"experiment_id": "unassigned", "scenario": None},
        )
        telemetry_id, duplicate = self.db.insert_telemetry(
            item, quality_status, str(experiment.get("experiment_id", "unassigned"))
        )
        if duplicate:
            return self._ack(quality_status, duplicate=True)

        rows = self.db.get_recent_telemetry(payload.device_id, timestamp, minutes=65)
        features, feature_status = build_features(rows, self.settings.expected_interval_seconds)

        event: dict[str, Any] = {
            "type": "telemetry",
            "telemetry_id": telemetry_id,
            "device_id": payload.device_id,
            "sequence_no": payload.sequence_no,
            "timestamp": payload.timestamp.isoformat(),
            "water_level_cm": payload.water_level_cm,
            "rain_rate_mmh": payload.rain_rate_mmh,
            "rain_interval_mm": payload.rain_interval_mm,
            "quality_status": quality_status,
            "features": features,
            "forecast_15m_cm": None,
            "forecast_30m_cm": None,
            "alert_level": None,
            "alert_label": None,
            "main_factor": None,
            "safety_override": False,
            "warning_level_cm": station["warning_level_cm"],
            "overflow_level_cm": station["overflow_level_cm"],
        }

        safety_override = payload.water_level_cm >= float(station["overflow_level_cm"])
        if quality_status != "valid" and not safety_override:
            event["quality_status"] = "unknown"
            self.broadcaster.publish_sync(event)
            return self._ack("unknown", duplicate=False)

        if features is None:
            features = features or {
                "rain_rate_mmh": payload.rain_rate_mmh,
                "rain_sum_5m": payload.rain_interval_mm,
                "water_level_cm": payload.water_level_cm,
                "water_rise_2m_cm": 0.0,
            }
        if feature_status == "valid":
            forecasts, version = self.registry.predict(features)
            main_factor = identify_main_factor(features)
        else:
            forecasts = {15: None, 30: None}
            version = "warming-up"
            main_factor = "Đang thu thập đủ lịch sử cảm biến"

        if safety_override:
            main_factor = "Mực nước hiện tại đã vượt ngưỡng nguy hiểm"

        alert_level, _ = self.alerts.evaluate(
            telemetry_id,
            payload.device_id,
            payload.timestamp.isoformat(),
            forecasts,
            features,
            station,
            main_factor,
        )
        self.db.save_forecast(
            telemetry_id,
            version,
            features,
            forecasts[15],
            forecasts[30],
            alert_level,
            main_factor,
            safety_override,
        )
        event["quality_status"] = "valid" if feature_status == "valid" else "warming_up"
        event["features"] = features
        event["forecast_15m_cm"] = forecasts[15]
        event["forecast_30m_cm"] = forecasts[30]
        event["alert_level"] = alert_level
        event["alert_label"] = ALERT_LABELS[alert_level]
        event["main_factor"] = main_factor
        event["safety_override"] = safety_override
        self.broadcaster.publish_sync(event)
        return self._ack(event["quality_status"], duplicate=False)

    @staticmethod
    def _ack(status: str, duplicate: bool) -> dict[str, Any]:
        return {
            "accepted": True,
            "duplicate": duplicate,
            "quality_status": status,
            "server_timestamp": datetime.now(timezone.utc),
        }
