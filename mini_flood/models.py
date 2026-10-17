from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from .config import FEATURE_NAMES, MiniFloodSettings


RISK_LABELS = {0: "An toàn", 1: "Cảnh báo", 2: "Nguy hiểm"}


def _probabilities_for_level(level: int) -> list[float]:
    mapping = {
        0: [0.85, 0.12, 0.03],
        1: [0.12, 0.76, 0.12],
        2: [0.03, 0.12, 0.85],
    }
    return mapping[level]


class BaselinePredictor:
    """Baseline minh bạch dùng trong giai đoạn chưa đủ dữ liệu huấn luyện."""

    def __init__(self, settings: MiniFloodSettings):
        self.settings = settings

    def predict_horizon(self, features: dict[str, float], horizon_minutes: int) -> dict[str, Any]:
        rise_per_minute = max(0.0, features["water_rise_15m_cm"] / 15.0)
        projected = features["water_level_cm"] + rise_per_minute * horizon_minutes
        if features["water_level_cm"] >= self.settings.danger_level_cm or projected >= self.settings.danger_level_cm:
            level = 2
        elif (
            features["water_level_cm"] >= self.settings.warning_level_cm
            or projected >= self.settings.warning_level_cm
            or features["rain_rate_mmh"] >= 30
            or features["water_rise_5m_cm"] >= 2
        ):
            level = 1
        else:
            level = 0
        return {
            "risk_level": level,
            "risk_label": RISK_LABELS[level],
            "probabilities": _probabilities_for_level(level),
        }


class MiniFloodModelRegistry:
    def __init__(self, settings: MiniFloodSettings):
        self.settings = settings
        self.baseline = BaselinePredictor(settings)
        self.models: dict[int, Any] = {}
        self.version = "mini-flood-baseline-v1"
        self._load()

    def _load(self) -> None:
        metadata_path = self.settings.model_dir / "mini_flood_metadata.json"
        metadata: dict[str, Any] = {}
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                metadata = {}
        if metadata.get("features") != list(FEATURE_NAMES):
            return

        loaded: dict[int, Any] = {}
        selected = metadata.get("selected_models", {})
        for horizon in (15, 30):
            if selected.get(str(horizon), "baseline") == "baseline":
                continue
            path = self.settings.model_dir / f"mini_flood_{horizon}m.joblib"
            if not path.exists():
                continue
            model = joblib.load(path)
            if list(getattr(model, "feature_names_in_", FEATURE_NAMES)) != list(FEATURE_NAMES):
                continue
            loaded[horizon] = model
        self.models = loaded
        self.version = str(metadata.get("model_version", "mini-flood-v1"))

    @property
    def ready(self) -> bool:
        return set(self.models) == {15, 30}

    def predict(self, features: dict[str, float]) -> tuple[dict[str, dict[str, Any]], str, bool]:
        predictions: dict[str, dict[str, Any]] = {}
        X = pd.DataFrame([[features[name] for name in FEATURE_NAMES]], columns=FEATURE_NAMES)
        for horizon in (15, 30):
            if horizon not in self.models:
                result = self.baseline.predict_horizon(features, horizon)
            else:
                model = self.models[horizon]
                level = int(model.predict(X)[0])
                raw_probs = model.predict_proba(X)[0]
                class_probs = {int(cls): float(prob) for cls, prob in zip(model.classes_, raw_probs)}
                result = {
                    "risk_level": level,
                    "risk_label": RISK_LABELS[level],
                    "probabilities": [round(class_probs.get(i, 0.0), 6) for i in (0, 1, 2)],
                }
            predictions[f"{horizon}m"] = result
        return predictions, self.version, not self.ready

    def danger_override(self) -> dict[str, dict[str, Any]]:
        item = {
            "risk_level": 2,
            "risk_label": RISK_LABELS[2],
            "probabilities": _probabilities_for_level(2),
        }
        return {"15m": dict(item), "30m": dict(item)}
