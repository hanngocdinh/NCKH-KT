from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import joblib
import pandas as pd
import sklearn
from datetime import datetime, timedelta
from time import perf_counter

from .ai_settings import FEATURE_NAMES
from .config import MiniFloodSettings

ALERT_LABELS = {0: "An toàn", 1: "Cảnh báo", 2: "Nguy hiểm"}


class MiniFloodModelRegistry:
    """Serve approved learned models only. Every failure is explicit, per horizon."""

    def __init__(self, settings: MiniFloodSettings):
        self.config = settings.ai
        self.runtime_mode = settings.runtime_mode
        self.data_source = "unknown"
        self.demo_approved = False
        self.model_dir = settings.model_dir
        self.models: dict[int, Any] = {}
        self.selected_models: dict[int, str | None] = {h: None for h in self.config.horizons_seconds}
        self.errors = {h: "metadata_missing" for h in self.config.horizons_seconds}
        self.artifact_hashes: dict[int, str] = {}
        self.version = "unavailable"
        self.promoted = False
        self._load()

    @property
    def ready(self) -> bool:
        return all(h in self.models for h in self.config.horizons_seconds)

    def _reject(self, reason: str) -> None:
        self.errors = {h: reason for h in self.config.horizons_seconds}

    def _load(self) -> None:
        path = self.model_dir / "mini_flood_metadata.json"
        if not path.exists():
            return
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                raise ValueError("metadata must be an object")
            self.version = str(metadata.get("model_version", "unavailable"))
            if metadata.get("features") != list(FEATURE_NAMES) or metadata.get("feature_signature") != self.config.feature_signature:
                self._reject("feature_signature_mismatch")
                return
            if metadata.get("horizons_seconds") != list(self.config.horizons_seconds):
                self._reject("horizons_mismatch")
                return
            self.promoted = metadata.get("promoted") is True and metadata.get("data_source") == "real"
            self.data_source = metadata.get("data_source", "unknown")
            self.demo_approved = metadata.get("demo_approved") is True and self.data_source == "synthetic"
            if self.demo_approved and metadata.get("evaluation_schema") != "alert-replay-v2":
                self._reject("demo_evaluation_schema_mismatch")
                return
            if not self.promoted and not (self.runtime_mode == "demo" and self.demo_approved):
                self._reject("model_not_approved")
                return
            versions = metadata.get("library_versions", {})
            if versions.get("scikit_learn", "").split(".")[:2] != sklearn.__version__.split(".")[:2]:
                self._reject("library_version_mismatch")
                return
            artifacts = metadata["artifacts"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._reject(f"metadata_invalid: {type(exc).__name__}")
            return
        for horizon in self.config.horizons_seconds:
            try:
                spec = artifacts[str(horizon)]
                if spec["algorithm"] not in {"ridge", "random_forest"}:
                    raise ValueError("unsupported_algorithm")
                artifact = (self.model_dir / spec["file"]).resolve()
                if artifact.parent != self.model_dir.resolve():
                    raise ValueError("artifact_outside_bundle")
                actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
                if actual != spec["sha256"]:
                    raise ValueError("artifact_hash_mismatch")
                model = joblib.load(artifact)
                if list(getattr(model, "feature_names_in_", [])) != list(FEATURE_NAMES):
                    raise ValueError("artifact_features_mismatch")
                self.models[horizon] = model
                self.selected_models[horizon] = spec["algorithm"]
                self.artifact_hashes[horizon] = actual
                self.errors.pop(horizon, None)
            except Exception as exc:
                self.errors[horizon] = f"artifact_invalid: {type(exc).__name__}: {exc}"

    def empty_result(self, status: str, reason: str | None) -> dict[str, Any]:
        return {
            "status": status, "mode": "model", "model_version": self.version,
            "config_hash": self.config.config_hash, "reason": reason, "ood": False,
            "schema_version": 2, "runtime_mode": self.runtime_mode,
            "data_source": self.data_source, "demo_approved": self.demo_approved,
            "forecasts": [
                {"horizon_seconds": h, "horizon_minutes": h / 60 if h % 60 == 0 else None,
                 "target_timestamp": None, "level_cm": None, "upper_p90_cm": None,
                 "algorithm": self.selected_models[h], "model_version": self.version,
                 "artifact_hash": self.artifact_hashes.get(h),
                 "status": status, "error": reason}
                for h in self.config.horizons_seconds
            ],
        }

    def predict_detailed(self, features: dict[str, float], measured_at: datetime | None = None) -> dict[str, Any]:
        started = perf_counter()
        result = self.empty_result("model_unavailable", None)
        X = pd.DataFrame([[features[name] for name in FEATURE_NAMES]], columns=FEATURE_NAMES)
        for item in result["forecasts"]:
            h = item["horizon_seconds"]
            if measured_at is not None:
                item["target_timestamp"] = (measured_at + timedelta(seconds=h)).isoformat()
            if h not in self.models:
                item["error"] = self.errors.get(h, "artifact_missing")
                continue
            try:
                value = float(self.models[h].predict(X)[0])
                if not math.isfinite(value):
                    raise ValueError("prediction_not_finite")
                item.update(level_cm=round(max(0.0, value), self.config.output_decimals), status="ready", error=None)
            except Exception as exc:
                item.update(status="prediction_failed", error=f"{type(exc).__name__}: {exc}")
        statuses = {item["status"] for item in result["forecasts"]}
        result["status"] = ("prediction_failed" if "prediction_failed" in statuses else
                            "model_unavailable" if "model_unavailable" in statuses else "ready")
        result["predict_ms"] = (perf_counter() - started) * 1000
        return result
