from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .config import MiniFloodSettings
from .db import MiniFloodDatabase
from .features import build_features, identify_main_factor
from .models import MiniFloodModelRegistry, RISK_LABELS
from .notifications import AlertManager, DeliveryWorker
from .schemas import TelemetryPayload


class MiniFloodService:
    def __init__(self, settings: MiniFloodSettings):
        self.settings = settings
        self.db = MiniFloodDatabase(settings.database_path)
        self.registry = MiniFloodModelRegistry(settings)
        self.alerts = AlertManager(self.db, settings)
        self.delivery_worker = DeliveryWorker(self.db)

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
            existing = self.db.get_prediction(telemetry_id)
            if existing:
                return self._response_from_prediction(existing, quality_status, duplicate=True)
            return self._base_response("warming_up", duplicate=True)

        rows = self.db.get_recent_telemetry(payload.device_id, timestamp, minutes=65)
        features, feature_status = build_features(rows, self.settings.expected_interval_seconds)

        if payload.water_level_cm >= self.settings.danger_level_cm:
            features = features or {
                "rain_rate_mmh": payload.rain_rate_mmh,
                "rain_sum_5m": payload.rain_interval_mm,
                "rain_sum_15m": payload.rain_interval_mm,
                "rain_sum_30m": payload.rain_interval_mm,
                "water_level_cm": payload.water_level_cm,
                "water_rise_5m_cm": 0.0,
                "water_rise_15m_cm": 0.0,
                "missing_ratio_15m": 1.0,
            }
            predictions = self.registry.danger_override()
            version = f"{self.registry.version}+safety-rule"
            main_factor = "Mực nước hiện tại đã vượt ngưỡng nguy hiểm"
            rule_override = True
        elif quality_status != "valid":
            return self._base_response("unknown", duplicate=False)
        elif feature_status != "valid" or features is None:
            return self._base_response("warming_up", duplicate=False)
        else:
            predictions, version, _ = self.registry.predict(features)
            main_factor = identify_main_factor(features)
            rule_override = False

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
        return {
            "accepted": True,
            "duplicate": False,
            "quality_status": "valid",
            "server_timestamp": datetime.now(timezone.utc),
            "predictions": predictions,
            "model_version": version,
            "main_factor": main_factor,
            "rule_override": rule_override,
        }

    @staticmethod
    def _response_from_prediction(existing: dict[str, Any], quality_status: str, duplicate: bool) -> dict[str, Any]:
        predictions = existing["predictions"]
        for value in predictions.values():
            value["risk_label"] = RISK_LABELS[int(value["risk_level"])]
        return {
            "accepted": True,
            "duplicate": duplicate,
            "quality_status": quality_status,
            "server_timestamp": datetime.now(timezone.utc),
            "predictions": predictions,
            "model_version": existing["model_version"],
            "main_factor": existing["main_factor"],
            "rule_override": existing["rule_override"],
        }

    @staticmethod
    def _base_response(status: str, duplicate: bool) -> dict[str, Any]:
        return {
            "accepted": True,
            "duplicate": duplicate,
            "quality_status": status,
            "server_timestamp": datetime.now(timezone.utc),
            "predictions": None,
            "model_version": None,
            "main_factor": None,
            "rule_override": False,
        }
