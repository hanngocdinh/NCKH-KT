# -*- coding: utf-8 -*-
"""
train_ai_model.py
=============================================================================
HỆ THỐNG HUẤN LUYỆN, ĐÁNH GIÁ & ĐÓNG GÓI MÔ HÌNH AI CẢNH BÁO NGẬP LỤT HỘI AN
(Đề tài AI + IoT Trường THPT Trần Quý Cáp)

Tính năng chính:
  1. Nạp và kiểm định tập dữ liệu đã làm giàu (hoian_flood_ai_dataset_prepared.csv).
  2. Huấn luyện 3 thuật toán: Logistic Regression (Scaled), Decision Tree, Random Forest.
  3. Đánh giá đa chiều: Stratified K-Fold Cross-Validation, Phân tầng Train/Test, Phân chia Thời gian.
  4. Tự động đóng gói & lưu trữ các mô hình tốt nhất vào thư mục `models/` (.joblib).
  5. Xuất siêu dữ liệu `models/model_metadata.json` và bảng xếp hạng `models/training_benchmark_results.csv`.
  6. Xuất biểu đồ ma trận nhầm lẫn đối đầu `models/evaluation_confusion_matrices.png`.
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np
import joblib

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.model_selection import train_test_split, StratifiedKFold, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix

DATASET_PREPARED = Path("hoian_flood_ai_dataset_prepared.csv")
DATASET_RAW = Path("hoian_flood_ai_dataset_365days.csv")
MODELS_DIR = Path("models")

FEATURES_LEAD24 = [
    "rain_daily_mm",
    "rain_max_hourly_mmh",
    "rain_3d_accum_mm",
    "rain_7d_accum_mm",
    "water_level_cm",
    "delta_water_level_cm",
    "river_discharge_m3s",
    "discharge_3d_mean_m3s",
    "delta_discharge_m3s",
]

FEATURES_SENSORLESS = [
    "rain_daily_mm",
    "rain_max_hourly_mmh",
    "rain_3d_accum_mm",
    "rain_7d_accum_mm",
    "river_discharge_m3s",
    "discharge_3d_mean_m3s",
]


def setup_models():
    """Khởi tạo cấu trúc các mô hình với tham số chuẩn hóa và bù trọng số."""
    return {
        "Logistic Regression (Scaled)": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42))
        ]),
        "Decision Tree (Balanced)": DecisionTreeClassifier(
            max_depth=5, class_weight="balanced", random_state=42
        ),
        "Random Forest (Balanced)": RandomForestClassifier(
            n_estimators=100, max_depth=6, class_weight="balanced", random_state=42
        ),
    }


def evaluate_with_cross_validation(X: pd.DataFrame, y: pd.Series, models: dict) -> pd.DataFrame:
    """Đánh giá 5-Fold Stratified Cross-Validation để kiểm tra tính ổn định."""
    print("\n" + "=" * 75)
    print("ĐÁNH GIÁ ỔN ĐỊNH BẰNG 5-FOLD STRATIFIED CROSS-VALIDATION")
    print("=" * 75)

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scoring = {
        "accuracy": "accuracy",
        "f1_macro": "f1_macro",
        "f1_weighted": "f1_weighted",
    }

    cv_results = []
    for name, model in models.items():
        scores = cross_validate(model, X, y, cv=skf, scoring=scoring)
        acc_mean = scores["test_accuracy"].mean() * 100
        acc_std = scores["test_accuracy"].std() * 100
        f1_m_mean = scores["test_f1_macro"].mean() * 100
        f1_w_mean = scores["test_f1_weighted"].mean() * 100

        print(f"-> {name:<30} | Accuracy: {acc_mean:5.2f}% ± {acc_std:4.2f}% | F1-Macro: {f1_m_mean:5.2f}% | F1-Weighted: {f1_w_mean:5.2f}%")
        cv_results.append({
            "Mô hình": name,
            "CV_Accuracy_Mean": round(acc_mean, 2),
            "CV_Accuracy_Std": round(acc_std, 2),
            "CV_F1_Macro_Mean": round(f1_m_mean, 2),
            "CV_F1_Weighted_Mean": round(f1_w_mean, 2),
        })

    return pd.DataFrame(cv_results)


def train_evaluate_scenario(name: str, X: pd.DataFrame, y: pd.Series, split_type: str = "stratified"):
    """Huấn luyện và đánh giá chi tiết trên tập Train/Test."""
    print("\n" + "-" * 75)
    print(f"KIỂM THỬ: {name.upper()} ({split_type.upper()})")
    print("-" * 75)

    if split_type == "temporal":
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    else:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

    models = setup_models()
    summary_rows = []
    trained_artifacts = {}

    for m_name, model in models.items():
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        trained_artifacts[m_name] = (model, y_pred)

        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, average="weighted", zero_division=0)
        rec = recall_score(y_test, y_pred, average="weighted", zero_division=0)
        f1_w = f1_score(y_test, y_pred, average="weighted", zero_division=0)
        f1_m = f1_score(y_test, y_pred, average="macro", zero_division=0)
        rec_flood = recall_score(y_test, y_pred, labels=[2], average="macro", zero_division=0)
        prec_flood = precision_score(y_test, y_pred, labels=[2], average="macro", zero_division=0)

        summary_rows.append({
            "Kịch bản": name,
            "Chia tập": split_type,
            "Mô hình": m_name,
            "Accuracy": round(acc * 100, 2),
            "Precision": round(prec * 100, 2),
            "Recall": round(rec * 100, 2),
            "F1-Weighted": round(f1_w * 100, 2),
            "F1-Macro": round(f1_m * 100, 2),
            "Recall_Lũ_Lớn": round(rec_flood * 100, 2),
            "Precision_Lũ_Lớn": round(prec_flood * 100, 2),
        })

    summary_df = pd.DataFrame(summary_rows)
    print(summary_df[["Mô hình", "Accuracy", "F1-Weighted", "F1-Macro", "Recall_Lũ_Lớn"]].to_string(index=False))

    return summary_df, trained_artifacts, y_test


def plot_confusion_matrices(trained_artifacts: dict, y_test: pd.Series, out_path: Path):
    """Xuất hình ảnh ma trận nhầm lẫn so sánh trực quan giữa các mô hình."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    classes = [0, 1, 2]
    class_names = ["0: An toàn", "1: Có nguy cơ", "2: Lũ lớn"]

    for idx, (m_name, (model, y_pred)) in enumerate(trained_artifacts.items()):
        cm = confusion_matrix(y_test, y_pred, labels=classes)
        sns.heatmap(
            cm,
            annot=True,
            fmt="d",
            cmap="Blues" if idx != 0 else "Greens",
            cbar=False,
            ax=axes[idx],
            xticklabels=class_names,
            yticklabels=class_names,
        )
        axes[idx].set_title(f"{m_name}\nRecall Lũ lớn: {recall_score(y_test, y_pred, labels=[2], average='macro', zero_division=0)*100:.1f}%")
        axes[idx].set_xlabel("AI Dự báo")
        axes[idx].set_ylabel("Thực tế")

    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()
    print(f"-> Đã lưu biểu đồ ma trận nhầm lẫn: {out_path.resolve()}")


def save_production_models(X: pd.DataFrame, y: pd.Series):
    """Huấn luyện trên toàn bộ dữ liệu và lưu mô hình sản phẩm vào models/."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print("\n" + "=" * 75)
    print("TIẾN HÀNH ĐÓNG GÓI MÔ HÌNH VÀO THƯ MỤC `models/`")
    print("=" * 75)

    models = setup_models()

    # 1. Đóng gói Logistic Regression (Mô hình An toàn Sinh mạng số 1)
    lr_pipe = models["Logistic Regression (Scaled)"]
    lr_pipe.fit(X[FEATURES_LEAD24], y)
    lr_file = MODELS_DIR / "model_lead24h_logistic_regression.joblib"
    joblib.dump(lr_pipe, lr_file)
    print(f"  * Đã đóng gói: {lr_file.name} (Pipeline StandardScaler + LogisticRegression)")

    # 2. Đóng gói Random Forest (Mô hình Độ chính xác cao & Feature Importance)
    rf_model = models["Random Forest (Balanced)"]
    rf_model.fit(X[FEATURES_LEAD24], y)
    rf_file = MODELS_DIR / "model_lead24h_random_forest.joblib"
    joblib.dump(rf_model, rf_file)
    print(f"  * Đã đóng gói: {rf_file.name} (Random Forest 100 cây)")

    # 3. Đóng gói Decision Tree cho bài toán Thủy văn Sensorless (Không mực nước)
    dt_model = models["Decision Tree (Balanced)"]
    dt_model.fit(X[FEATURES_SENSORLESS], y)
    dt_file = MODELS_DIR / "model_sensorless_decision_tree.joblib"
    joblib.dump(dt_model, dt_file)
    print(f"  * Đã đóng gói: {dt_file.name} (Decision Tree Sensorless)")

    # 4. Xuất Metadata lưu vết kiến trúc & cấu hình
    metadata = {
        "project": "AI + IoT Dự báo Nguy cơ Ngập lụt Hội An (THPT Trần Quý Cáp)",
        "timestamp": datetime.now().isoformat(),
        "dataset_rows": len(X),
        "target_variable": "target_lead24h",
        "classes": {
            0: "An toàn (Dưới BĐ1 < 2.0m)",
            1: "Có nguy cơ (BĐ1 - BĐ2: 2.0m - 3.0m)",
            2: "Lũ nguy cơ cao (Trên BĐ2 >= 3.0m)"
        },
        "lead24h_features": FEATURES_LEAD24,
        "sensorless_features": FEATURES_SENSORLESS,
        "legacy_reference_model": "model_lead24h_logistic_regression.joblib",
        "deployment_status": "legacy_reference_only",
        "safety_guarantee": "none; the reported class-2 recall was measured on too few temporal holdout samples",
    }
    meta_file = MODELS_DIR / "model_metadata.json"
    meta_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  * Đã xuất siêu dữ liệu: {meta_file.name}")


def main():
    parser = argparse.ArgumentParser(description="Hệ thống Huấn luyện & Đóng gói Model AI Cảnh báo Ngập Hội An")
    parser.add_argument("--save", action="store_true", default=True, help="Tự động lưu mô hình vào thư mục models/")
    args = parser.parse_args()

    print("=" * 75)
    print("KHỞI CHẠY SETUP HUẤN LUYỆN TOÀN DIỆN MÔ HÌNH MACHINE LEARNING")
    print("=" * 75)

    target_file = DATASET_PREPARED if DATASET_PREPARED.exists() else DATASET_RAW
    if not target_file.exists():
        print(f"Lỗi: Không tìm thấy tệp {target_file}! Hãy chạy analyze_and_prepare_dataset.py trước.")
        return

    df = pd.read_csv(target_file)
    print(f"-> Đã nạp thành công: {target_file} ({len(df)} dòng, {len(df.columns)} cột)")

    X = df.copy()
    y = df["target_lead24h"].astype(int)

    # 1. Chạy Cross-Validation
    cv_df = evaluate_with_cross_validation(X[FEATURES_LEAD24], y, setup_models())

    # 2. Đánh giá Train/Test Stratified & Temporal
    all_summaries = []
    sum_strat, artifacts_strat, y_test_strat = train_evaluate_scenario(
        "Cảnh báo sớm 24h (t -> t+1)", X[FEATURES_LEAD24], y, split_type="stratified"
    )
    all_summaries.append(sum_strat)

    sum_temp, _, _ = train_evaluate_scenario(
        "Cảnh báo sớm 24h (t -> t+1)", X[FEATURES_LEAD24], y, split_type="temporal"
    )
    all_summaries.append(sum_temp)

    # 3. Đánh giá bài toán Thủy văn Sensorless
    y_same = df["flood_risk_label"].astype(int)
    sum_sensorless, _, _ = train_evaluate_scenario(
        "Mô hình Thủy văn Sensorless (Không mực nước)", X[FEATURES_SENSORLESS], y_same, split_type="stratified"
    )
    all_summaries.append(sum_sensorless)

    # Xuất bảng tổng hợp kết quả Benchmark ra CSV
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    full_benchmark_df = pd.concat(all_summaries, ignore_index=True)
    benchmark_csv = MODELS_DIR / "training_benchmark_results.csv"
    full_benchmark_df.to_csv(benchmark_csv, index=False, encoding="utf-8-sig")
    print(f"\n-> Đã lưu bảng xếp hạng hiệu năng: {benchmark_csv.resolve()}")

    # Xuất biểu đồ ma trận nhầm lẫn
    cm_plot_path = MODELS_DIR / "evaluation_confusion_matrices.png"
    plot_confusion_matrices(artifacts_strat, y_test_strat, cm_plot_path)

    # 4. Đóng gói mô hình sản xuất
    if args.save:
        save_production_models(X, y)

    print("\n" + "=" * 75)
    print("HOÀN TẤT THÀNH CÔNG SETUP HUẤN LUYỆN & ĐÓNG GÓI MODEL!")
    print(f"Các mô hình sẵn sàng sử dụng trong thư mục: {MODELS_DIR.resolve()}")
    print("=" * 75)


if __name__ == "__main__":
    main()
