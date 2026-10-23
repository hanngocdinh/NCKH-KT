from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


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
    default_device_id: str = "mini-flood-station-01"
    default_overflow_level_cm: float = 40.0
    default_warning_margin_cm: float = 10.0
    default_hysteresis_cm: float = 2.0
    default_recovery_hold_seconds: int = 120
    reminder_minutes: int = 30
    expected_interval_seconds: int = 60
    notification_worker_enabled: bool = True
    notification_poll_seconds: int = 15
    mdns_enabled: bool = False
    mdns_hostname: str = "mini-flood-backend"
    mdns_port: int = 8000

    @classmethod
    def from_env(cls) -> "MiniFloodSettings":
        return cls(
            database_path=Path(os.getenv("MINI_FLOOD_DB", "mini_flood.sqlite3")),
            model_dir=Path(os.getenv("MINI_FLOOD_MODEL_DIR", "models")),
            device_api_key=os.getenv("MINI_FLOOD_DEVICE_KEY", "change-me"),
            default_device_id=os.getenv("MINI_FLOOD_DEFAULT_DEVICE_ID", "mini-flood-station-01"),
            default_overflow_level_cm=float(os.getenv("MINI_FLOOD_DEFAULT_OVERFLOW_CM", "40")),
            default_warning_margin_cm=float(os.getenv("MINI_FLOOD_DEFAULT_WARNING_MARGIN_CM", "10")),
            default_hysteresis_cm=float(os.getenv("MINI_FLOOD_DEFAULT_HYSTERESIS_CM", "2")),
            default_recovery_hold_seconds=int(os.getenv("MINI_FLOOD_DEFAULT_RECOVERY_HOLD_SECONDS", "120")),
            reminder_minutes=int(os.getenv("MINI_FLOOD_REMINDER_MINUTES", "30")),
            expected_interval_seconds=int(os.getenv("MINI_FLOOD_INTERVAL_SECONDS", "60")),
            notification_worker_enabled=_env_bool("MINI_FLOOD_NOTIFICATION_WORKER", True),
            notification_poll_seconds=int(os.getenv("MINI_FLOOD_NOTIFICATION_POLL_SECONDS", "15")),
            mdns_enabled=_env_bool("MINI_FLOOD_MDNS_ENABLED", True),
            mdns_hostname=os.getenv("MINI_FLOOD_MDNS_HOSTNAME", "mini-flood-backend")
            .removesuffix(".local"),
            mdns_port=int(os.getenv("MINI_FLOOD_MDNS_PORT", "8000")),
        )
