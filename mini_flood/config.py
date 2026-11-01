from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from .ai_settings import AIConfig, load_ai_config
from .notification_settings import NotificationConfig, load_notification_config
from .schemas import StationConfigUpdate

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass



def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class MiniFloodSettings:
    database_path: Path = Path("mini_flood.sqlite3")
    model_dir: Path = Path("models/current")
    device_api_key: str = "change-me"
    default_device_id: str = "mini-flood-station-01"
    default_overflow_level_cm: float = 40.0
    default_warning_margin_cm: float = 10.0
    default_hysteresis_cm: float = 2.0
    default_recovery_hold_seconds: int = 120
    reminder_minutes: int = 30
    ai: AIConfig = field(default_factory=load_ai_config)
    runtime_mode: str = "real"
    notifications: NotificationConfig = field(default_factory=load_notification_config)
    notification_worker_enabled: bool = True
    notification_poll_seconds: float | None = None
    mdns_enabled: bool = False
    mdns_hostname: str = "mini-flood-backend"
    mdns_port: int = 8000

    def __post_init__(self):
        if self.runtime_mode not in {"real", "demo"}:
            raise ValueError("MINI_FLOOD_MODE must be real or demo")
        if self.notification_poll_seconds is not None and self.notification_poll_seconds <= 0:
            raise ValueError("Notification poll interval must be positive")
        StationConfigUpdate(overflow_level_cm=self.default_overflow_level_cm,
                            warning_margin_cm=self.default_warning_margin_cm,
                            hysteresis_cm=self.default_hysteresis_cm,
                            recovery_hold_seconds=self.default_recovery_hold_seconds)

    @classmethod
    def from_env(cls) -> "MiniFloodSettings":
        return cls(
            database_path=Path(os.getenv("MINI_FLOOD_DB", "mini_flood.sqlite3")),
            model_dir=Path(os.getenv("MINI_FLOOD_MODEL_DIR", "models/current")),
            runtime_mode=os.getenv("MINI_FLOOD_MODE", "real"),
            device_api_key=os.getenv("MINI_FLOOD_DEVICE_KEY", "change-me"),
            default_device_id=os.getenv("MINI_FLOOD_DEFAULT_DEVICE_ID", "mini-flood-station-01"),
            default_overflow_level_cm=float(os.getenv("MINI_FLOOD_DEFAULT_OVERFLOW_CM", "40")),
            default_warning_margin_cm=float(os.getenv("MINI_FLOOD_DEFAULT_WARNING_MARGIN_CM", "10")),
            default_hysteresis_cm=float(os.getenv("MINI_FLOOD_DEFAULT_HYSTERESIS_CM", "2")),
            default_recovery_hold_seconds=int(os.getenv("MINI_FLOOD_DEFAULT_RECOVERY_HOLD_SECONDS", "120")),
            reminder_minutes=int(os.getenv("MINI_FLOOD_REMINDER_MINUTES", "30")),
            notification_worker_enabled=_env_bool("MINI_FLOOD_NOTIFICATION_WORKER", True),
            notification_poll_seconds=(float(os.environ["MINI_FLOOD_NOTIFICATION_POLL_SECONDS"])
                                       if "MINI_FLOOD_NOTIFICATION_POLL_SECONDS" in os.environ else None),
            mdns_enabled=_env_bool("MINI_FLOOD_MDNS_ENABLED", True),
            mdns_hostname=os.getenv("MINI_FLOOD_MDNS_HOSTNAME", "mini-flood-backend")
            .removesuffix(".local"),
            mdns_port=int(os.getenv("MINI_FLOOD_MDNS_PORT", "8000")),
        )
