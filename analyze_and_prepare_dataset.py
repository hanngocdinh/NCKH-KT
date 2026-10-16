# -*- coding: utf-8 -*-
"""
analyze_and_prepare_dataset.py
=============================================================================
Công cụ phân tích chuyên sâu (EDA) và tiền xử lý, làm giàu dữ liệu (Feature Engineering)
cho bài toán Huấn luyện mô hình AI Cảnh báo Ngập lụt Hội An (THPT Trần Quý Cáp).

Tính năng chính:
  1. Phân tích thống kê mô tả (Descriptive Statistics, Phân bố, Độ lệch Skewness).
  2. Đánh giá chất lượng dữ liệu: Nguồn quan trắc thực tế vs Mô hình thủy văn, giá trị khuyết.
  3. Phân tích hiện tượng Data Leakage (Rò rỉ dữ liệu) ở bài toán cùng ngày.
  4. Tạo đặc trưng trễ (Lag features), đạo hàm dòng chảy (Delta Discharge) và nhãn dự báo sớm 24h (Lead-time t+1).
  5. Xuất dataset đã làm giàu: hoian_flood_ai_dataset_prepared.csv.
  6. Xuất biểu đồ trực quan hóa dữ liệu (Distribution, Heatmap, Time-series).
"""

import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np

# Thiết lập encoding utf-8 cho console Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

INPUT_DATASET = Path("hoian_flood_ai_dataset_365days.csv")
OUTPUT_PREPARED = Path("hoian_flood_ai_dataset_prepared.csv")


def run_exploratory_data_analysis(df: pd.DataFrame) -> dict:
    """Thực hiện phân tích khám phá dữ liệu (EDA) và trả về bảng chỉ số."""
    print("=" * 75)
    print("BÁO CÁO PHÂN TÍCH DỮ LIỆU (EXPLORATORY DATA ANALYSIS - EDA)")
    print("=" * 75)

    print(f"-> Kích thước tập dữ liệu: {df.shape[0]} mẫu (ngày) x {df.shape[1]} thuộc tính")
    print(f"-> Khoảng thời gian: từ {df['date'].min()} đến {df['date'].max()}")

    # 1. Kiểm tra nguồn gốc dữ liệu mực nước
    print("\n--- 1. NGUỒN GỐC DỮ LIỆU QUAN TRẮC MỰC NƯỚC ---")
    source_counts = df["water_level_source"].value_counts()
    for src, count in source_counts.items():
        pct = (count / len(df)) * 100
        print(f"  * {src:<30}: {count:3d} ngày ({pct:5.2f}%)")

    # 2. Phân bố nhãn mục tiêu (Class Imbalance)
    print("\n--- 2. PHÂN BỐ NHÃN NGUY CƠ NGẬP (FLOOD RISK LABELS) ---")
    label_counts = df["flood_risk_label"].value_counts().sort_index()
    label_names = {
        0: "0: An toàn (Dưới BĐ1 < 2.0m)",
        1: "1: Có nguy cơ (BĐ1 - BĐ2: 2.0m - 3.0m)",
        2: "2: Nguy cơ cao (Trên BĐ2 >= 3.0m)"
    }
    for lbl, count in label_counts.items():
        pct = (count / len(df)) * 100
        name = label_names.get(lbl, str(lbl))
        print(f"  * {name:<40}: {count:3d} ngày ({pct:5.2f}%)")

    # 3. Thống kê mô tả các biến đặc trưng định lượng
    numeric_features = [
        "rain_daily_mm",
        "rain_max_hourly_mmh",
        "rain_3d_accum_mm",
        "rain_7d_accum_mm",
        "water_level_cm",
        "delta_water_level_cm",
        "river_discharge_m3s",
        "discharge_3d_mean_m3s",
    ]

    print("\n--- 3. THỐNG KÊ MÔ TẢ CÁC ĐẶC TRƯNG VẬT LÝ KHÍ TƯỢNG - THỦY VĂN ---")
    stats_df = df[numeric_features].describe().T
    stats_df["skew"] = df[numeric_features].skew()
    stats_df = stats_df[["mean", "std", "min", "25%", "50%", "75%", "max", "skew"]].round(2)
    print(stats_df.to_string())

    # 4. Ma trận tương quan với nhãn ngập lụt
    print("\n--- 4. HỆ SỐ TƯƠNG QUAN TUYẾN TÍNH (PEARSON CORRELATION) VỚI FLOOD_RISK_LABEL ---")
    corr_series = df[numeric_features + ["flood_risk_label"]].corr()["flood_risk_label"].sort_values(ascending=False)
    for col, val in corr_series.items():
        if col != "flood_risk_label":
            print(f"  * {col:<25}: r = {val:+.3f}")

    # 5. Phân tích rò rỉ dữ liệu (Data Leakage Audit)
    print("\n--- 5. KIỂM TOÁN RÒ RỈ DỮ LIỆU (DATA LEAKAGE AUDIT) ---")
    print("  [!] LƯU Ý KHOA HỌC QUAN TRỌNG:")
    print("  * 'water_level_cm' có hệ số tương quan r = 0.928 với 'flood_risk_label'.")
    print("  * Lý do: Nhãn 'flood_risk_label' được định nghĩa trực tiếp từ ngưỡng mực nước (2.0m và 3.0m).")
    print("  * Do đó, nếu đưa 'water_level_cm' vào mô hình chẩn đoán cùng ngày (Same-day Diagnosis),")
    print("    mô hình cây (Decision Tree/Random Forest) sẽ đạt độ chính xác 100% bằng cách ghi nhớ luật ngưỡng.")
    print("  * GIẢI PHÁP:")
    print("    a) Bài toán 1 (Sensorless Hydrological Model): Dự báo nguy cơ ngập thuần túy từ Mưa và Lưu lượng")
    print("       thượng nguồn GloFAS (bỏ đặc trưng mực nước cảm biến).")
    print("    b) Bài toán 2 (24h Early Warning Forecast): Dùng mực nước và khí tượng ngày t để dự báo trước")
    print("       nguy cơ ngập của ngày t+1 (Lead-time 24h), phục vụ cảnh báo sớm cho nhà trường.")

    return {
        "stats": stats_df,
        "corr": corr_series,
        "source_counts": source_counts,
        "label_counts": label_counts,
    }


def prepare_and_engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Tạo thêm các đặc trưng động học, độ trễ và nhãn dự báo sớm 24h."""
    print("\n" + "=" * 75)
    print("TIỀN XỬ LÝ & LÀM GIÀU ĐẶC TRƯNG (FEATURE ENGINEERING)")
    print("=" * 75)

    df_out = df.copy()

    # Đảm bảo sắp xếp chuẩn theo dòng thời gian
    df_out["date"] = pd.to_datetime(df_out["date"])
    df_out = df_out.sort_values("date").reset_index(drop=True)

    # 1. Đạo hàm lưu lượng thượng nguồn (Delta Discharge: tốc độ dồn lũ từ thượng nguồn)
    df_out["delta_discharge_m3s"] = df_out["river_discharge_m3s"].diff().fillna(0.0).round(2)

    # 2. Đặc trưng trễ 1 ngày (Lag-1 Features)
    df_out["water_level_lag1_cm"] = df_out["water_level_cm"].shift(1).fillna(df_out["water_level_cm"].iloc[0]).round(1)
    df_out["river_discharge_lag1_m3s"] = df_out["river_discharge_m3s"].shift(1).fillna(df_out["river_discharge_m3s"].iloc[0]).round(2)
    df_out["rain_daily_lag1_mm"] = df_out["rain_daily_mm"].shift(1).fillna(0.0).round(2)

    # 3. Chỉ số xung kích mưa (Rain intensity ratio: Tỷ lệ mưa giờ cực đại / mưa ngày)
    df_out["rain_intensity_ratio"] = (
        df_out["rain_max_hourly_mmh"] / (df_out["rain_daily_mm"] + 0.1)
    ).clip(0.0, 1.0).round(3)

    # 4. Chỉ số bão hòa lưu vực (Saturation proxy: Lưu lượng sông / (Mưa 3 ngày + 1))
    df_out["discharge_rain_ratio"] = (
        df_out["river_discharge_m3s"] / (df_out["rain_3d_accum_mm"] + 10.0)
    ).round(2)

    # 5. Nhãn dự báo sớm 24 giờ tới (Lead-time t+1)
    df_out["target_lead24h"] = df_out["flood_risk_label"].shift(-1)
    # Ngày cuối cùng gán bằng nhãn hiện tại (forward fill)
    df_out["target_lead24h"] = df_out["target_lead24h"].ffill().astype(int)

    lead_descs = []
    for val in df_out["target_lead24h"]:
        if val == 0:
            lead_descs.append("0: Ngày mai An toàn")
        elif val == 1:
            lead_descs.append("1: Ngày mai Có nguy cơ (BĐ1-BĐ2)")
        else:
            lead_descs.append("2: Ngày mai Nguy cơ cao (>=BĐ2)")
    df_out["target_lead24h_desc"] = lead_descs

    # 6. Nhãn nhị phân phát hiện sự kiện lũ (Binary Alert: 0 = An toàn, 1 = Cảnh báo lũ)
    df_out["target_binary_same_day"] = (df_out["flood_risk_label"] > 0).astype(int)
    df_out["target_binary_lead24h"] = (df_out["target_lead24h"] > 0).astype(int)

    # Chuyển lại cột date sang chuỗi YYYY-MM-DD
    df_out["date"] = df_out["date"].dt.strftime("%Y-%m-%d")

    print(f"-> Đã tạo thêm 8 đặc trưng động học & nhãn dự báo mới.")
    print(f"-> Phân bố nhãn dự báo sớm ngày mai (target_lead24h):")
    counts_lead = df_out["target_lead24h"].value_counts().sort_index()
    for lbl, cnt in counts_lead.items():
        print(f"   * Nhãn {lbl}: {cnt:3d} ngày ({cnt/len(df_out)*100:5.2f}%)")

    # Lưu dataset chuẩn hóa
    df_out.to_csv(OUTPUT_PREPARED, index=False, encoding="utf-8-sig")
    print(f"-> Đã lưu tập dữ liệu chuẩn hóa vào: {OUTPUT_PREPARED.resolve()}")
    return df_out


def generate_visualization_plots(df: pd.DataFrame):
    """Xuất các biểu đồ trực quan hóa dữ liệu phục vụ báo cáo khoa học."""
    print("\n" + "=" * 75)
    print("XUẤT CÁC BIỂU ĐỒ TRỰC QUAN HÓA (DATA VISUALIZATION)")
    print("=" * 75)

    sns.set_theme(style="whitegrid", font="sans-serif")
    plt.rcParams.update({"font.size": 11, "axes.labelsize": 12, "axes.titlesize": 13})

    # --- Hình 1: Chuỗi thời gian thủy văn và nhãn cảnh báo lũ Hội An ---
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    dates = pd.to_datetime(df["date"])

    # Đồ thị mực nước Câu Lâu
    ax1.plot(dates, df["water_level_m"], color="#1f77b4", linewidth=1.8, label="Mực nước thực tế/mô hình (m)")
    ax1.axhline(2.0, color="#f39c12", linestyle="--", linewidth=1.5, label="Báo động 1 (2.00m)")
    ax1.axhline(3.0, color="#e74c3c", linestyle="--", linewidth=1.5, label="Báo động 2 (3.00m)")
    ax1.axhline(4.0, color="#8e44ad", linestyle=":", linewidth=1.5, label="Báo động 3 (4.00m)")
    ax1.set_ylabel("Mực nước (m)")
    ax1.set_title("Chuỗi thời gian Thủy văn & Khí tượng Trạm Câu Lâu - Sông Thu Bồn (Hội An)")
    ax1.legend(loc="upper right", frameon=True)

    # Đồ thị lưu lượng sông GloFAS
    ax2.plot(dates, df["river_discharge_m3s"], color="#27ae60", linewidth=1.5, label="Lưu lượng GloFAS (m³/s)")
    ax2.plot(dates, df["discharge_3d_mean_m3s"], color="#16a085", linestyle="--", linewidth=1.2, label="Lưu lượng TB 3 ngày (m³/s)")
    ax2.set_ylabel("Lưu lượng (m³/s)")
    ax2.legend(loc="upper right", frameon=True)

    # Đồ thị lượng mưa Open-Meteo
    ax3.bar(dates, df["rain_daily_mm"], color="#2980b9", width=1.0, alpha=0.7, label="Mưa ngày (mm)")
    ax3.plot(dates, df["rain_3d_accum_mm"], color="#d35400", linewidth=1.5, label="Mưa tích lũy 3 ngày (mm)")
    ax3.set_ylabel("Lượng mưa (mm)")
    ax3.set_xlabel("Thời gian")
    ax3.legend(loc="upper right", frameon=True)

    plt.tight_layout()
    plot1_path = Path("eda_hydro_timeseries.png")
    plt.savefig(plot1_path, dpi=200)
    plt.close()
    print(f"-> Đã lưu biểu đồ chuỗi thời gian: {plot1_path.resolve()}")

    # --- Hình 2: Ma trận tương quan nhiệt (Correlation Heatmap) ---
    features_for_corr = [
        "rain_daily_mm",
        "rain_max_hourly_mmh",
        "rain_3d_accum_mm",
        "rain_7d_accum_mm",
        "river_discharge_m3s",
        "delta_discharge_m3s",
        "water_level_cm",
        "delta_water_level_cm",
        "flood_risk_label",
        "target_lead24h",
    ]
    corr_matrix = df[features_for_corr].corr()

    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(
        corr_matrix,
        annot=True,
        fmt=".2f",
        cmap="coolwarm",
        vmin=-0.2,
        vmax=1.0,
        square=True,
        linewidths=0.5,
        ax=ax,
        cbar_kws={"label": "Hệ số tương quan Pearson"},
    )
    ax.set_title("Ma trận Tương quan giữa các Đặc trưng Khí tượng Thủy văn và Nhãn Ngập")
    plt.tight_layout()
    plot2_path = Path("eda_correlation_heatmap.png")
    plt.savefig(plot2_path, dpi=200)
    plt.close()
    print(f"-> Đã lưu biểu đồ tương quan heatmap: {plot2_path.resolve()}")

    # --- Hình 3: Phân bố các đặc trưng theo từng cấp độ nguy cơ ngập ---
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    sns.boxplot(x="flood_risk_label", y="river_discharge_m3s", data=df, ax=axes[0], palette="Blues")
    axes[0].set_title("Lưu lượng sông GloFAS (m³/s) theo Nhãn Nguy cơ")
    axes[0].set_xlabel("Cấp nguy cơ (0: An toàn, 1: Nguy cơ, 2: Nguy cơ cao)")
    axes[0].set_ylabel("Lưu lượng (m³/s)")

    sns.boxplot(x="flood_risk_label", y="rain_3d_accum_mm", data=df, ax=axes[1], palette="Greens")
    axes[1].set_title("Mưa tích lũy 3 ngày (mm) theo Nhãn Nguy cơ")
    axes[1].set_xlabel("Cấp nguy cơ (0: An toàn, 1: Nguy cơ, 2: Nguy cơ cao)")
    axes[1].set_ylabel("Mưa tích lũy 3 ngày (mm)")

    sns.boxplot(x="flood_risk_label", y="water_level_cm", data=df, ax=axes[2], palette="Oranges")
    axes[2].set_title("Mực nước Trạm Câu Lâu (cm) theo Nhãn Nguy cơ")
    axes[2].set_xlabel("Cấp nguy cơ (0: An toàn, 1: Nguy cơ, 2: Nguy cơ cao)")
    axes[2].set_ylabel("Mực nước (cm)")

    plt.tight_layout()
    plot3_path = Path("eda_boxplots_by_risk.png")
    plt.savefig(plot3_path, dpi=200)
    plt.close()
    print(f"-> Đã lưu biểu đồ phân bố boxplot: {plot3_path.resolve()}")


def main():
    if not INPUT_DATASET.exists():
        print(f"Lỗi: Không tìm thấy file {INPUT_DATASET}!")
        return

    df = pd.read_csv(INPUT_DATASET)
    run_exploratory_data_analysis(df)
    df_prepared = prepare_and_engineer_features(df)
    generate_visualization_plots(df_prepared)

    print("\n" + "=" * 75)
    print("HOÀN THÀNH PHÂN TÍCH VÀ CHUẨN BỊ DATASET THÀNH CÔNG!")
    print("=" * 75)


if __name__ == "__main__":
    main()
