from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TelemetryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1, le=1)
    device_id: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    # Mỗi lần thiết bị khởi động có một boot_id mới. Giá trị mặc định chỉ để
    # các client V2 cũ tiếp tục hoạt động; firmware mới luôn gửi trường này.
    boot_id: str = Field(
        default="legacy", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
    )
    sequence_no: int = Field(ge=0)
    timestamp: datetime
    rain_interval_mm: float = Field(ge=0, le=500)
    rain_rate_mmh: float = Field(ge=0, le=1000)
    water_level_cm: float = Field(ge=0, le=500)
    quality_flags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("timestamp")
    @classmethod
    def timestamp_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp phải có múi giờ")
        return value

    @field_validator("quality_flags")
    @classmethod
    def normalize_flags(cls, value: list[str]) -> list[str]:
        flags = []
        for item in value:
            normalized = item.strip().lower().replace(" ", "_")
            if normalized and normalized not in flags:
                flags.append(normalized[:64])
        return flags


class TelemetryResponse(BaseModel):
    accepted: bool
    duplicate: bool = False
    quality_status: str
    server_timestamp: datetime


class ExperimentStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    experiment_id: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    scenario: str = Field(pattern=r"^(normal|warning|danger)$")


class StationConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overflow_level_cm: float = Field(gt=0, le=1000)
    warning_margin_cm: float = Field(gt=0, le=1000)
    hysteresis_cm: float = Field(ge=0, le=100)
    recovery_hold_seconds: int = Field(ge=0, le=86400)

    @model_validator(mode="after")
    def validate_relationships(self) -> "StationConfigUpdate":
        warning_level = self.overflow_level_cm - self.warning_margin_cm
        if warning_level <= 0:
            raise ValueError("warning_margin_cm phải nhỏ hơn overflow_level_cm")
        if self.hysteresis_cm >= min(warning_level, self.warning_margin_cm):
            raise ValueError(
                "hysteresis_cm phải nhỏ hơn cả ngưỡng cảnh báo và vùng đệm cảnh báo"
            )
        return self
