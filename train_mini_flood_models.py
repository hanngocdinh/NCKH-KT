"""Huấn luyện model dự báo 15/30 phút từ dữ liệu thí nghiệm mô hình mini.

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
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score
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


def risk_from_level(level: float, warning: float, danger: float) -> int:
    if level >= danger:
        return 2
    if level >= warning:
        return 1
    return 0


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
                end = current_time + pd.Timedelta(minutes=horizon)
                future = group[(group["timestamp"] > current_time) & (group["timestamp"] <= end)]
                if future.empty or future["timestamp"].max() < end - pd.Timedelta(seconds=settings.expected_interval_seconds * 0.5):
                    complete = False
                    break
                max_level = float(future["water_level_cm"].max())
                record[f"target_{horizon}m"] = risk_from_level(
                    max_level, settings.warning_level_cm, settings.danger_level_cm
                )
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
        "macro_f1": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 6),
        "danger_recall": round(float(recall_score(y_true, y_pred, labels=[2], average="macro", zero_division=0)), 6),
        "danger_precision": round(float(precision_score(y_true, y_pred, labels=[2], average="macro", zero_division=0)), 6),
    }


def baseline_predictions(features: pd.DataFrame, horizon: int, settings: MiniFloodSettings) -> np.ndarray:
    baseline = BaselinePredictor(settings)
    return np.array(
        [baseline.predict_horizon(row.to_dict(), horizon)["risk_level"] for _, row in features.iterrows()]
    )


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
        target = f"target_{horizon}m"
        X_train = train_df[list(FEATURE_NAMES)]
        y_train = train_df[target].astype(int)
        X_test = test_df[list(FEATURE_NAMES)]
        y_test = test_df[target].astype(int)

        candidates = {
            "logistic_regression": Pipeline(
                [
                    ("scaler", StandardScaler()),
                    ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)),
                ]
            ),
            "random_forest": RandomForestClassifier(
                n_estimators=200,
                max_depth=8,
                min_samples_leaf=2,
                class_weight="balanced",
                random_state=42,
            ),
        }
        baseline_pred = baseline_predictions(X_test, horizon, settings)
        baseline_metrics = evaluate(y_test, baseline_pred)
        all_metrics.append({"horizon": horizon, "model": "baseline", **baseline_metrics})

        best_name = "baseline"
        best_model = None
        best_metrics = baseline_metrics
        best_pred = baseline_pred
        for name, model in candidates.items():
            model.fit(X_train, y_train)
            pred = model.predict(X_test)
            metrics = evaluate(y_test, pred)
            all_metrics.append({"horizon": horizon, "model": name, **metrics})
            eligible = (
                metrics["macro_f1"] > baseline_metrics["macro_f1"]
                and metrics["danger_recall"] >= baseline_metrics["danger_recall"]
            )
            if eligible and metrics["macro_f1"] > best_metrics["macro_f1"]:
                best_name, best_model, best_metrics, best_pred = name, model, metrics, pred

        selected[horizon] = best_name
        if best_model is not None:
            joblib.dump(best_model, output_dir / f"mini_flood_{horizon}m.joblib")
        else:
            stale = output_dir / f"mini_flood_{horizon}m.joblib"
            if stale.exists():
                stale.unlink()

        cm = confusion_matrix(y_test, best_pred, labels=[0, 1, 2])
        axis.imshow(cm, cmap="Blues")
        axis.set_title(f"{horizon} phút — {best_name}")
        axis.set_xlabel("Dự báo")
        axis.set_ylabel("Thực tế")
        axis.set_xticks([0, 1, 2])
        axis.set_yticks([0, 1, 2])
        for i in range(3):
            for j in range(3):
                axis.text(j, i, int(cm[i, j]), ha="center", va="center")

    plt.tight_layout()
    plt.savefig(output_dir / "mini_flood_confusion_matrices.png", dpi=180)
    plt.close(fig)
    pd.DataFrame(all_metrics).to_csv(output_dir / "mini_flood_benchmark.csv", index=False)

    learned_ready = all(name != "baseline" for name in selected.values())
    metadata = {
        "model_version": f"mini-flood-v1-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "created_at": datetime.now().astimezone().isoformat(),
        "features": list(FEATURE_NAMES),
        "horizons_minutes": [15, 30],
        "warning_level_cm": settings.warning_level_cm,
        "danger_level_cm": settings.danger_level_cm,
        "selected_models": {str(k): v for k, v in selected.items()},
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
    parser = argparse.ArgumentParser(description="Train model mô hình mini dự báo ngập 15/30 phút")
    parser.add_argument("--input", type=Path, required=True, help="CSV telemetry có experiment_id")
    parser.add_argument("--output-dir", type=Path, default=Path("models"))
    args = parser.parse_args()
    metadata = train(args.input, args.output_dir, MiniFloodSettings.from_env())
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
