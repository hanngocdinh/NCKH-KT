"""Huấn luyện model hồi quy mực nước sau 15/30 phút từ dữ liệu thí nghiệm.

CSV đầu vào cần có: experiment_id, device_id, sequence_no, timestamp,
rain_interval_mm, rain_rate_mmh, water_level_cm, quality_flags.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from mini_flood.config import FEATURE_NAMES, MiniFloodSettings
from mini_flood.features import build_features
from mini_flood.models import BaselinePredictor


REQUIRED_COLUMNS = {
    "experiment_id",
    "device_id",
    "sequence_no",
    "timestamp",
    "rain_interval_mm",
    "rain_rate_mmh",
    "water_level_cm",
}


def build_training_dataset(
    raw: pd.DataFrame,
    settings: MiniFloodSettings,
) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS - set(raw.columns)
    if missing:
        raise ValueError(f"Thiếu cột bắt buộc: {sorted(missing)}")
    data = raw.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    if "quality_flags" not in data:
        data["quality_flags"] = "[]"
    output: list[dict] = []

    for experiment_id, group in data.groupby("experiment_id", sort=False):
        group = group.sort_values(["timestamp", "sequence_no"]).reset_index(drop=True)
        rows: list[dict] = []
        for _, source in group.iterrows():
            rows.append(
                {
                    "device_id": str(source["device_id"]),
                    "sequence_no": int(source["sequence_no"]),
                    "timestamp": source["timestamp"].isoformat(),
                    "rain_interval_mm": float(source["rain_interval_mm"]),
                    "rain_rate_mmh": float(source["rain_rate_mmh"]),
                    "water_level_cm": float(source["water_level_cm"]),
                    "quality_status": "valid",
                }
            )
            features, status = build_features(rows[-66:], settings.expected_interval_seconds)
            if status != "valid" or features is None:
                continue
            current_time = source["timestamp"]
            record = {"experiment_id": str(experiment_id), "timestamp": current_time, **features}
            complete = True
            for horizon in (15, 30):
                target_time = current_time + pd.Timedelta(minutes=horizon)
                deltas = (group["timestamp"] - target_time).abs()
                nearest_index = deltas.idxmin()
                if deltas.loc[nearest_index] > pd.Timedelta(seconds=settings.expected_interval_seconds):
                    complete = False
                    break
                target_row = group.loc[nearest_index]
                if target_row["timestamp"] <= current_time:
                    complete = False
                    break
                record[f"target_{horizon}m_cm"] = float(target_row["water_level_cm"])
            if complete:
                output.append(record)
    return pd.DataFrame(output)


def chronological_experiment_split(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    order = (
        data.groupby("experiment_id")["timestamp"]
        .min()
        .sort_values()
        .index.tolist()
    )
    if len(order) < 3:
        raise ValueError("Cần ít nhất 3 experiment_id độc lập để train/test")
    test_count = max(1, int(np.ceil(len(order) * 0.2)))
    train_ids = set(order[:-test_count])
    test_ids = set(order[-test_count:])
    return data[data["experiment_id"].isin(train_ids)], data[data["experiment_id"].isin(test_ids)]


def evaluate(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    return {
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 6),
        "rmse": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 6),
        "r2": round(float(r2_score(y_true, y_pred)), 6) if len(y_true) > 1 else 0.0,
    }


def baseline_outputs(
    features: pd.DataFrame,
    horizon: int,
    settings: MiniFloodSettings,
) -> np.ndarray:
    baseline = BaselinePredictor()
    outputs = [baseline.predict_horizon(row.to_dict(), horizon) for _, row in features.iterrows()]
    return np.asarray(outputs, dtype=float)


def train(input_csv: Path, output_dir: Path, settings: MiniFloodSettings) -> dict:
    raw = pd.read_csv(input_csv)
    data = build_training_dataset(raw, settings)
    if data.empty:
        raise ValueError("Không tạo được mẫu có đủ lịch sử và nhãn tương lai")
    train_df, test_df = chronological_experiment_split(data)
    output_dir.mkdir(parents=True, exist_ok=True)
    all_metrics: list[dict] = []
    selected: dict[int, str] = {}

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for axis, horizon in zip(axes, (15, 30)):
        target = f"target_{horizon}m_cm"
        X_train = train_df[list(FEATURE_NAMES)]
        y_train = train_df[target].astype(float)
        X_test = test_df[list(FEATURE_NAMES)]
        y_test = test_df[target].astype(float)

        candidates = {
            "ridge": Pipeline([("scaler", StandardScaler()), ("regressor", Ridge(alpha=1.0))]),
            "random_forest": RandomForestRegressor(
                n_estimators=200,
                max_depth=4,
                min_samples_leaf=2,
                random_state=42,
            ),
        }
        baseline_pred = baseline_outputs(X_test, horizon, settings)
        baseline_metrics = evaluate(y_test, baseline_pred)
        all_metrics.append({"horizon": horizon, "model": "baseline", **baseline_metrics})

        fitted: dict[str, object] = {}
        predictions: dict[str, np.ndarray] = {}
        candidate_metrics: dict[str, dict[str, float]] = {}
        for name, model in candidates.items():
            model.fit(X_train, y_train)
            pred = np.maximum(0.0, model.predict(X_test))
            metrics = evaluate(y_test, pred)
            fitted[name] = model
            predictions[name] = pred
            candidate_metrics[name] = metrics
            all_metrics.append({"horizon": horizon, "model": name, **metrics})

        candidate_name = min(candidate_metrics, key=lambda name: candidate_metrics[name]["mae"])
        eligible = candidate_metrics[candidate_name]["mae"] < baseline_metrics["mae"]
        best_name = candidate_name if eligible else "baseline"
        best_model = fitted[best_name] if eligible else None
        best_pred = predictions[best_name] if eligible else baseline_pred

        selected[horizon] = best_name
        if best_model is not None:
            joblib.dump(best_model, output_dir / f"mini_flood_{horizon}m.joblib")
        else:
            stale = output_dir / f"mini_flood_{horizon}m.joblib"
            if stale.exists():
                stale.unlink()

        axis.scatter(y_test, best_pred, alpha=0.65)
        bounds = [float(min(y_test.min(), best_pred.min())), float(max(y_test.max(), best_pred.max()))]
        axis.plot(bounds, bounds, "--", color="gray")
        axis.set_title(f"{horizon} phút — {best_name}")
        axis.set_xlabel("Mực nước thực tế (cm)")
        axis.set_ylabel("Mực nước dự báo (cm)")

    plt.tight_layout()
    plt.savefig(output_dir / "mini_flood_regression_validation.png", dpi=180)
    plt.close(fig)
    pd.DataFrame(all_metrics).to_csv(output_dir / "mini_flood_benchmark.csv", index=False)

    learned_ready = all(name != "baseline" for name in selected.values())
    metadata = {
        "model_version": f"mini-flood-v2-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "created_at": datetime.now().astimezone().isoformat(),
        "features": list(FEATURE_NAMES),
        "horizons_minutes": [15, 30],
        "selected_models": {str(k): v for k, v in selected.items()},
        "algorithm_policy": "lowest_mae_of_ridge_random_forest_if_better_than_baseline",
        "learned_models_ready": learned_ready,
        "train_experiments": sorted(train_df["experiment_id"].unique().tolist()),
        "test_experiments": sorted(test_df["experiment_id"].unique().tolist()),
        "training_rows": len(train_df),
        "test_rows": len(test_df),
        "disclaimer": "Kết quả mô phỏng thử nghiệm, chưa đại diện cho hệ thống cảnh báo thực tế Hội An.",
    }
    (output_dir / "mini_flood_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return metadata


def main() -> None:
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Train model hồi quy mực nước sau 15/30 phút")
    parser.add_argument("--input", type=Path, required=True, help="CSV telemetry có experiment_id")
    parser.add_argument("--output-dir", type=Path, default=Path("models"))
    args = parser.parse_args()
    metadata = train(args.input, args.output_dir, MiniFloodSettings.from_env())
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
