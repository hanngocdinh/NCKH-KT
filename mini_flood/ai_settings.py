"""Validated inference settings; model training is outside the runtime package."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


FEATURE_NAMES = ("rain_rate_mmh", "rain_sum_window_mm", "water_level_cm", "water_delta_window_cm")


class StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DataConfig(StrictConfig):
    expected_interval_seconds: int = Field(gt=0)
    rain_window_seconds: int = Field(gt=0)
    rise_window_seconds: int = Field(gt=0)
    max_gap_seconds: int = Field(gt=0)
    lookup_tolerance_seconds: int = Field(ge=0)
    live_max_age_seconds: int = Field(gt=0)
    future_tolerance_seconds: int = Field(ge=0)
    clock_min_timestamp: datetime
    offline_timeout_seconds: int = Field(gt=0)

    @model_validator(mode="after")
    def coherent_windows(self):
        if self.clock_min_timestamp.tzinfo is None:
            raise ValueError("clock_min_timestamp requires timezone")
        if self.expected_interval_seconds > min(self.rain_window_seconds, self.rise_window_seconds):
            raise ValueError("feature windows must cover at least one sample interval")
        if self.max_gap_seconds < self.expected_interval_seconds:
            raise ValueError("max_gap_seconds must cover expected_interval_seconds")
        return self


class ExplanationConfig(StrictConfig):
    heavy_rain_rate_mmh: float = Field(ge=0)
    heavy_rain_sum_mm: float = Field(ge=0)
    fast_rise_cm: float = Field(ge=0)


class AIConfig(StrictConfig):
    horizons_seconds: tuple[int, ...]
    data: DataConfig
    explanation: ExplanationConfig
    output_decimals: int = Field(ge=0)

    @model_validator(mode="after")
    def valid_horizons(self):
        if not self.horizons_seconds or any(h <= 0 for h in self.horizons_seconds):
            raise ValueError("horizons_seconds must be positive")
        if tuple(sorted(set(self.horizons_seconds))) != self.horizons_seconds:
            raise ValueError("horizons_seconds must be unique and sorted")
        return self

    @property
    def config_hash(self) -> str:
        raw = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()

    @property
    def feature_signature(self) -> str:
        raw = json.dumps({
            "features": FEATURE_NAMES,
            "schema_version": "window-features-v1",
            "units": ["mm/h", "mm", "cm", "cm"],
            "rain_window_seconds": self.data.rain_window_seconds,
            "rise_window_seconds": self.data.rise_window_seconds,
            "expected_interval_seconds": self.data.expected_interval_seconds,
            "max_gap_seconds": self.data.max_gap_seconds,
            "lookup_tolerance_seconds": self.data.lookup_tolerance_seconds,
            "output_decimals": self.output_decimals,
        }, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()


def load_ai_config(path: Path | str | None = None) -> AIConfig:
    resolved = Path(path or os.getenv("MINI_FLOOD_AI_CONFIG") or Path(__file__).resolve().parents[1] / "config" / "ai.json")
    return AIConfig.model_validate_json(resolved.read_text(encoding="utf-8"))
