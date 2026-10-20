from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .broadcaster import broadcaster
from .config import MiniFloodSettings
from .db import MiniFloodDatabase
from .features import build_features, identify_main_factor
from .models import MiniFloodModelRegistry
from .notifications import AlertManager, DeliveryWorker
from .schemas import TelemetryPayload


class MiniFloodService:
    def __init__(self, settings: MiniFloodSettings):
        self.settings = settings
        self.db = MiniFloodDatabase(settings.database_path)
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
        item = payload.model_dump(mode="json")
        timestamp = payload.timestamp
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
            "predictions": None,
            "main_factor": None,
            "rule_override": False,
        }

        if payload.water_level_cm >= self.settings.danger_level_cm:
            features = features or {
                "rain_rate_mmh": payload.rain_rate_mmh,
                "rain_sum_5m": payload.rain_interval_mm,
                "water_level_cm": payload.water_level_cm,
                "water_rise_2m_cm": 0.0,
            }
            predictions = self.registry.danger_override()
            version = f"{self.registry.version}+safety-rule"
            main_factor = "Mực nước hiện tại đã vượt ngưỡng nguy hiểm"
            rule_override = True
        elif quality_status != "valid":
            event["quality_status"] = "unknown"
            self.broadcaster.publish_sync(event)
            return self._ack("unknown", duplicate=False)
        elif feature_status != "valid" or features is None:
            event["quality_status"] = "warming_up"
            self.broadcaster.publish_sync(event)
            return self._ack("warming_up", duplicate=False)
        else:
            predictions, version, rule_override = self.registry.predict(features)
            main_factor = identify_main_factor(features)

        self.db.save_prediction(
            telemetry_id, version, features, predictions, main_factor, rule_override
        )
        self.alerts.evaluate(
            telemetry_id,
            payload.device_id,
            payload.timestamp.isoformat(),
            predictions,
            features,
            main_factor,
        )
        event["quality_status"] = "valid"
        event["features"] = features
        event["predictions"] = predictions
        event["main_factor"] = main_factor
        event["rule_override"] = rule_override
        self.broadcaster.publish_sync(event)
        return self._ack("valid", duplicate=False)

    @staticmethod
    def _ack(status: str, duplicate: bool) -> dict[str, Any]:
        return {
            "accepted": True,
            "duplicate": duplicate,
            "quality_status": status,
            "server_timestamp": datetime.now(timezone.utc),
        }
