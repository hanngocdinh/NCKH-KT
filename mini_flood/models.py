from __future__ import annotations

import json
from typing import Any

import joblib
import pandas as pd

from .config import FEATURE_NAMES, MiniFloodSettings


ALERT_LABELS = {0: "An toàn", 1: "Cảnh báo", 2: "Nguy hiểm"}


class BaselinePredictor:
    """Baseline hồi quy minh bạch: chiếu tuyến tính tốc độ dâng gần nhất."""

    @staticmethod
    def predict_horizon(features: dict[str, float], horizon_minutes: int) -> float:
        rise_per_minute = float(features["water_rise_2m_cm"]) / 2.0
        projected = float(features["water_level_cm"]) + rise_per_minute * horizon_minutes
        return round(max(0.0, projected), 4)


class MiniFloodModelRegistry:
    def __init__(self, settings: MiniFloodSettings):
        self.settings = settings
        self.baseline = BaselinePredictor()
        self.models: dict[int, Any] = {}
        self.selected_models: dict[int, str] = {15: "baseline", 30: "baseline"}
        self.version = "mini-flood-regression-baseline-v2"
        self._load()

    def _load(self) -> None:
        metadata_path = self.settings.model_dir / "mini_flood_metadata.json"
        if not metadata_path.exists():
            return
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if metadata.get("features") != list(FEATURE_NAMES):
            return

        selected = metadata.get("selected_models", {})
        loaded: dict[int, Any] = {}
        for horizon in (15, 30):
            name = str(selected.get(str(horizon), "baseline"))
            if name not in {"ridge", "random_forest", "baseline"}:
                continue
            self.selected_models[horizon] = name
            if name == "baseline":
                continue
            path = self.settings.model_dir / f"mini_flood_{horizon}m.joblib"
            if not path.exists():
                self.selected_models[horizon] = "baseline"
                continue
            try:
                model = joblib.load(path)
            except (OSError, ValueError, TypeError):
                self.selected_models[horizon] = "baseline"
                continue
            if list(getattr(model, "feature_names_in_", FEATURE_NAMES)) != list(FEATURE_NAMES):
                self.selected_models[horizon] = "baseline"
                continue
            loaded[horizon] = model
        self.models = loaded
        self.version = str(metadata.get("model_version", self.version))

    @property
    def ready(self) -> bool:
        return set(self.models) == {15, 30}

    def predict(self, features: dict[str, float]) -> tuple[dict[int, float], str]:
        X = pd.DataFrame([[features[name] for name in FEATURE_NAMES]], columns=FEATURE_NAMES)
        forecasts: dict[int, float] = {}
        for horizon in (15, 30):
            model = self.models.get(horizon)
            if model is None:
                value = self.baseline.predict_horizon(features, horizon)
            else:
                value = float(model.predict(X)[0])
            forecasts[horizon] = round(max(0.0, value), 4)
        return forecasts, self.version
