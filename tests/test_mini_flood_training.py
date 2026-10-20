from datetime import datetime, timedelta, timezone

import pandas as pd

from mini_flood.config import MiniFloodSettings
from train_mini_flood_models import build_training_dataset, train


def synthetic_experiments():
    rows = []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for experiment in range(5):
        for minute in range(100):
            if minute < 50:
                level = 6 + minute * 0.05
                rain = 2
            elif minute < 70:
                level = 8.5 + (minute - 50) * 0.5
                rain = 35
            else:
                level = 18.5 + (minute - 70) * 0.6
                rain = 50
            rows.append(
                {
                    "experiment_id": f"run-{experiment}",
                    "device_id": "mini-flood-station-01",
                    "sequence_no": experiment * 1000 + minute,
                    "timestamp": (start + timedelta(days=experiment, minutes=minute)).isoformat(),
                    "rain_interval_mm": rain / 60,
                    "rain_rate_mmh": rain,
                    "water_level_cm": level,
                    "quality_flags": "[]",
                }
            )
    return pd.DataFrame(rows)


def test_training_builds_future_labels_without_last_rows(tmp_path):
    raw = synthetic_experiments()
    settings = MiniFloodSettings(
        database_path=tmp_path / "unused.sqlite3",
        model_dir=tmp_path / "models",
        notification_worker_enabled=False,
    )
    prepared = build_training_dataset(raw, settings)
    assert not prepared.empty
    assert {"target_15m", "target_30m"}.issubset(prepared.columns)
    for experiment_id, group in prepared.groupby("experiment_id"):
        source_end = pd.to_datetime(raw[raw["experiment_id"] == experiment_id]["timestamp"], utc=True).max()
        assert pd.to_datetime(group["timestamp"], utc=True).max() <= source_end - timedelta(minutes=30)

    csv_path = tmp_path / "experiments.csv"
    raw.to_csv(csv_path, index=False)
    metadata = train(csv_path, tmp_path / "models", settings)
    assert metadata["horizons_minutes"] == [15, 30]
    assert len(metadata["train_experiments"]) == 4
    assert len(metadata["test_experiments"]) == 1
    assert (tmp_path / "models" / "mini_flood_benchmark.csv").exists()
    assert (tmp_path / "models" / "mini_flood_confusion_matrices.png").exists()
