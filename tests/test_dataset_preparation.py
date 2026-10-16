# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path


def test_prepared_dataset_integrity():
    prepared_file = Path("hoian_flood_ai_dataset_prepared.csv")
    assert prepared_file.exists(), "hoian_flood_ai_dataset_prepared.csv does not exist!"

    df = pd.read_csv(prepared_file)
    assert len(df) == 366, f"Expected 366 rows, got {len(df)}"

    required_cols = [
        "date",
        "rain_daily_mm",
        "rain_max_hourly_mmh",
        "rain_3d_accum_mm",
        "rain_7d_accum_mm",
        "water_level_cm",
        "delta_water_level_cm",
        "river_discharge_m3s",
        "discharge_3d_mean_m3s",
        "delta_discharge_m3s",
        "water_level_lag1_cm",
        "river_discharge_lag1_m3s",
        "flood_risk_label",
        "target_lead24h",
        "target_binary_same_day",
        "target_binary_lead24h",
    ]
    for col in required_cols:
        assert col in df.columns, f"Missing required column: {col}"
        assert df[col].isnull().sum() == 0, f"Column {col} has null values!"

    # Kiểm tra tính hợp lệ của nhãn mục tiêu
    for col in ["flood_risk_label", "target_lead24h"]:
        unique_labels = set(df[col].unique())
        assert unique_labels.issubset({0, 1, 2}), f"Invalid labels in {col}: {unique_labels}"

    # Kiểm tra tính đơn điệu của thời gian
    dates = pd.to_datetime(df["date"])
    assert dates.is_monotonic_increasing, "Dataset dates must be monotonically increasing!"
