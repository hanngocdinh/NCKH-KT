# -*- coding: utf-8 -*-
from pathlib import Path
import joblib
import pandas as pd
import numpy as np


def test_production_models_exist_and_infer():
    models_dir = Path("models")
    assert models_dir.exists(), "models directory does not exist!"

    lr_file = models_dir / "model_lead24h_logistic_regression.joblib"
    rf_file = models_dir / "model_lead24h_random_forest.joblib"
    dt_file = models_dir / "model_sensorless_decision_tree.joblib"

    assert lr_file.exists(), f"Missing {lr_file}"
    assert rf_file.exists(), f"Missing {rf_file}"
    assert dt_file.exists(), f"Missing {dt_file}"

    # Kiểm tra nạp và suy luận của Logistic Regression
    lr_model = joblib.load(lr_file)
    features_9 = [
        "rain_daily_mm", "rain_max_hourly_mmh", "rain_3d_accum_mm", "rain_7d_accum_mm",
        "water_level_cm", "delta_water_level_cm", "river_discharge_m3s", "discharge_3d_mean_m3s",
        "delta_discharge_m3s"
    ]
    sample_df = pd.DataFrame([{f: 10.0 for f in features_9}])
    pred_lr = lr_model.predict(sample_df)[0]
    prob_lr = lr_model.predict_proba(sample_df)[0]
    assert pred_lr in [0, 1, 2]
    assert np.isclose(prob_lr.sum(), 1.0)

    # Kiểm tra nạp và suy luận của Random Forest
    rf_model = joblib.load(rf_file)
    pred_rf = rf_model.predict(sample_df)[0]
    prob_rf = rf_model.predict_proba(sample_df)[0]
    assert pred_rf in [0, 1, 2]
    assert np.isclose(prob_rf.sum(), 1.0)

    # Kiểm tra nạp và suy luận của Decision Tree Sensorless (6 features)
    dt_model = joblib.load(dt_file)
    features_6 = [
        "rain_daily_mm", "rain_max_hourly_mmh", "rain_3d_accum_mm", "rain_7d_accum_mm",
        "river_discharge_m3s", "discharge_3d_mean_m3s"
    ]
    sample_sensorless = pd.DataFrame([{f: 10.0 for f in features_6}])
    pred_dt = dt_model.predict(sample_sensorless)[0]
    assert pred_dt in [0, 1, 2]
