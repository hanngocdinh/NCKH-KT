from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


FEATURE_NAMES = (
    "rain_rate_mmh",
    "rain_sum_5m",
    "water_level_cm",
    "water_rise_2m_cm",
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class MiniFloodSettings:
    database_path: Path = Path("mini_flood.sqlite3")
    model_dir: Path = Path("models")
    device_api_key: str = "change-me"
    warning_level_cm: float = 15.0
    danger_level_cm: float = 25.0
    reminder_minutes: int = 30
    expected_interval_seconds: int = 60
    notification_worker_enabled: bool = True
    notification_poll_seconds: int = 15

    @classmethod
    def from_env(cls) -> "MiniFloodSettings":
        return cls(
            database_path=Path(os.getenv("MINI_FLOOD_DB", "mini_flood.sqlite3")),
            model_dir=Path(os.getenv("MINI_FLOOD_MODEL_DIR", "models")),
            device_api_key=os.getenv("MINI_FLOOD_DEVICE_KEY", "change-me"),
            warning_level_cm=float(os.getenv("MINI_FLOOD_WARNING_CM", "15")),
            danger_level_cm=float(os.getenv("MINI_FLOOD_DANGER_CM", "25")),
            reminder_minutes=int(os.getenv("MINI_FLOOD_REMINDER_MINUTES", "30")),
            expected_interval_seconds=int(os.getenv("MINI_FLOOD_INTERVAL_SECONDS", "60")),
            notification_worker_enabled=_env_bool("MINI_FLOOD_NOTIFICATION_WORKER", True),
            notification_poll_seconds=int(os.getenv("MINI_FLOOD_NOTIFICATION_POLL_SECONDS", "15")),
        )
