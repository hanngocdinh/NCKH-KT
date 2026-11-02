"""Validation helpers for rendering model output in the dashboard."""

from __future__ import annotations

import math
from typing import Any


def station_device_ids(payload: dict[str, Any] | None, default_device_id: str) -> list[str]:
    """Return unique station IDs from the API, with a safe default fallback."""
    items = payload.get("items") if isinstance(payload, dict) else None
    device_ids: list[str] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            device_id = item.get("device_id")
            if isinstance(device_id, str) and device_id and device_id not in device_ids:
                device_ids.append(device_id)
    if not device_ids:
        device_ids.append(default_device_id)
    return device_ids


def forecast_horizon_seconds(item: dict[str, Any]) -> int | None:
    """Return a positive whole-second horizon without guessing a unit."""
    raw = item.get("horizon_seconds")
    if raw is None:
        minutes = item.get("horizon_minutes")
        if minutes is None or isinstance(minutes, bool):
            return None
        try:
            raw = float(minutes) * 60
        except (TypeError, ValueError):
            return None
    if isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0 or not value.is_integer():
        return None
    return int(value)


def forecast_level_cm(item: dict[str, Any]) -> float | None:
    """Return a finite, non-negative model prediction or None."""
    raw = item.get("level_cm")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def select_model_forecasts(
    inference: dict[str, Any] | None,
    *,
    require_ready: bool = True,
) -> tuple[dict[int, dict[str, Any]], list[str]]:
    """Select only explicit, valid model forecasts for UI rendering.

    The function never creates horizons from configuration. It accepts only the
    entries present in the inference payload and reports every omitted entry.
    """
    if not isinstance(inference, dict):
        return {}, ["inference_missing"]
    if inference.get("mode") != "model":
        return {}, ["inference_mode_not_model"]
    raw_items = inference.get("forecasts")
    if not isinstance(raw_items, list):
        return {}, ["forecasts_not_list"]

    selected: dict[int, dict[str, Any]] = {}
    issues: list[str] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            issues.append(f"forecast_{index}_not_object")
            continue
        horizon = forecast_horizon_seconds(raw_item)
        if horizon is None:
            issues.append(f"forecast_{index}_invalid_horizon")
            continue
        status = raw_item.get("status")
        if require_ready and status != "ready":
            issues.append(f"forecast_{horizon}s_{status or 'status_missing'}")
            continue
        if not require_ready and status not in (None, "ready"):
            issues.append(f"forecast_{horizon}s_{status}")
            continue
        level = forecast_level_cm(raw_item)
        if level is None:
            issues.append(f"forecast_{horizon}s_invalid_level")
            continue
        if horizon in selected:
            issues.append(f"forecast_{horizon}s_duplicate")
            continue
        selected[horizon] = {
            **raw_item,
            "horizon_seconds": horizon,
            "level_cm": level,
        }
    return dict(sorted(selected.items())), issues
