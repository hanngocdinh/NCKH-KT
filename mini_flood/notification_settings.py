"""Delivery/UI tunables. Credentials remain in the environment."""
import json
import os
from pathlib import Path

from pydantic import Field, model_validator

from .ai_settings import StrictConfig


class NotificationConfig(StrictConfig):
    poll_seconds: float = Field(gt=0)
    timeout_seconds: float = Field(gt=0)
    retry_seconds: tuple[float, ...]
    message_ttl_seconds: float = Field(gt=0)
    claim_seconds: float = Field(gt=0)
    batch_size: int = Field(gt=0)
    dashboard_refresh_seconds: float = Field(gt=0)
    stream_queue_size: int = Field(gt=0)

    @model_validator(mode="after")
    def coherent(self):
        if any(delay <= 0 for delay in self.retry_seconds):
            raise ValueError("retry delays must be positive")
        if self.claim_seconds <= self.timeout_seconds:
            raise ValueError("claim must outlive a send timeout")
        return self


def load_notification_config() -> NotificationConfig:
    path = Path(os.getenv("MINI_FLOOD_NOTIFICATION_CONFIG") or
                Path(__file__).resolve().parents[1] / "config" / "notifications.json")
    return NotificationConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
