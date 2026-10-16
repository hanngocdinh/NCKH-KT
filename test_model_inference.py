# -*- coding: utf-8 -*-
"""
test_model_inference.py
=============================================================================
CÔNG CỤ KIỂM THỬ & SUY LUẬN MÔ HÌNH AI ĐÃ HUẤN LUYỆN
(Dự án AI + IoT Cảnh báo Sớm Ngập lụt Hội An - THPT Trần Quý Cáp)

Tính năng:
  - Nạp trực tiếp mô hình sản xuất từ thư mục models/:
      * Logistic Regression (Scaled + Balanced): Mô hình cứu sinh số 1 (Recall 100%)
      * Random Forest (Balanced): Mô hình độ chính xác cao
  - Hỗ trợ các chế độ thử nghiệm linh hoạt:
      [1] Thử nghiệm các kịch bản mẫu điển hình
      [2] Tự nhập thông số thời tiết tùy ý để dự báo
      [3] Thử nghiệm ngẫu nhiên trên các ngày lịch sử thực tế (Backtesting)
      [4] So sánh đối đầu song song Logistic Regression vs Random Forest
"""

import sys
import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import joblib

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

MODELS_DIR = Path("models")
LR_MODEL_FILE = MODELS_DIR / "model_lead24h_logistic_regression.joblib"
RF_MODEL_FILE = MODELS_DIR / "model_lead24h_random_forest.joblib"
DATASET_FILE = Path("hoian_flood_ai_dataset_prepared.csv")

FEATURE_COLS = [
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


def load_models():
    """Nạp cả 2 mô hình đã huấn luyện thành công."""
    if not LR_MODEL_FILE.exists() or not RF_MODEL_FILE.exists():
        print(f"Lỗi: Chưa tìm thấy mô hình trong {MODELS_DIR}! Hãy chạy `python train_ai_model.py` trước.")
        sys.exit(1)
    lr_model = joblib.load(LR_MODEL_FILE)
    rf_model = joblib.load(RF_MODEL_FILE)
    return lr_model, rf_model


def render_progress_bar(pct: float, width: int = 15) -> str:
    """Tạo thanh tiến trình phần trăm trực quan."""
    filled = int(round(pct * width))
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}] {pct * 100:5.1f}%"


def predict_single(model, model_name: str, input_dict: dict):
    """Thực hiện dự báo và in kết quả chi tiết."""
    input_df = pd.DataFrame([input_dict])[FEATURE_COLS]
    pred_label = int(model.predict(input_df)[0])
    probs = model.predict_proba(input_df)[0]

    status_map = {
        0: ("AN TOÀN (DƯỚI BÁO ĐỘNG 1)", "XANH", "Tắt", "Hoạt động dạy học bình thường."),
        1: ("CÓ NGUY CƠ NGẬP (BĐ1 - BĐ2)", "VÀNG", "Tắt", "Kê cao thiết bị phòng máy tầng 1, kiểm tra khơi thông cống rãnh."),
        2: ("NGUY CƠ CAO / LŨ LỚN (TRÊN BĐ2)", "ĐỎ (NHẤP NHÁY)", "HÚ CÒI BÁO ĐỘNG LIÊN TỤC", "THÔNG BÁO CHO HỌC SINH NGHỈ HỌC NGÀY MAI, ngắt cầu dao điện tầng 1."),
    }
    desc, led, buzzer, action = status_map[pred_label]

    print("\n" + "=" * 75)
    print(f"KẾT QUẢ SUY LUẬN AI: [{model_name.upper()}]")
    print("=" * 75)
    print("1. THÔNG SỐ VẬT LÝ NẠP VÀO MODEL:")
    print(f"   * Lượng mưa ngày / Mưa giờ cực đại : {input_dict['rain_daily_mm']:>6.1f} mm  | {input_dict['rain_max_hourly_mmh']:>5.1f} mm/h")
    print(f"   * Mưa tích lũy 3 ngày / 7 ngày     : {input_dict['rain_3d_accum_mm']:>6.1f} mm  | {input_dict['rain_7d_accum_mm']:>5.1f} mm")
    print(f"   * Mực nước hiện tại / Tốc độ dâng  : {input_dict['water_level_cm']:>6.1f} cm  | {input_dict['delta_water_level_cm']:>+5.1f} cm/ngày")
    print(f"   * Lưu lượng sông GloFAS / Biến thiên: {input_dict['river_discharge_m3s']:>6.1f} m³/s | {input_dict['delta_discharge_m3s']:>+5.1f} m³/s")

    print("\n2. DỰ BÁO NGUY CƠ CHO 24 GIỜ TIẾP THEO (LEAD-TIME 1,440 PHÚT):")
    print(f"   * Cấp độ cảnh báo  : LỚP {pred_label} -> {desc}")
    print(f"   * Xác suất An toàn : {render_progress_bar(probs[0])}")
    print(f"   * Xác suất Nguy cơ : {render_progress_bar(probs[1])}")
    print(f"   * Xác suất Lũ lớn  : {render_progress_bar(probs[2])}")

    print("\n3. PHẢN HỒI THIẾT BỊ PHẦN CỨNG (IoT Wokwi):")
    print(f"   * Đèn tín hiệu LED : {led}")
    print(f"   * Còi báo động     : {buzzer}")

    print("\n4. CHỈ ĐẠO ỨNG PHÓ CHO TRƯỜNG THPT TRẦN QUÝ CÁP:")
    print(f"   👉 {action}")
    print("=" * 75)
    return pred_label, probs


def compare_both_models(lr_model, rf_model, input_dict: dict, title: str = "So sánh đối đầu"):
    """Chạy đồng thời cả 2 mô hình để so sánh sự đồng thuận giữa các thuật toán."""
    input_df = pd.DataFrame([input_dict])[FEATURE_COLS]

    lr_pred = int(lr_model.predict(input_df)[0])
    lr_probs = lr_model.predict_proba(input_df)[0]

    rf_pred = int(rf_model.predict(input_df)[0])
    rf_probs = rf_model.predict_proba(input_df)[0]

    labels_desc = {0: "0: An toàn", 1: "1: Có nguy cơ", 2: "2: Lũ nguy cơ cao"}

    print("\n" + "=" * 75)
    print(f"SO SÁNH ĐỐI ĐẦU 2 MÔ HÌNH: [{title.upper()}]")
    print("=" * 75)
    print(f"{'Tiêu chí':<25} | {'Logistic Regression (Safety #1)':<25} | {'Random Forest (Accuracy #1)':<25}")
    print("-" * 75)
    print(f"{'Dự báo nguy cơ (Y)':<25} | {labels_desc[lr_pred]:<25} | {labels_desc[rf_pred]:<25}")
    print(f"{'Xác suất An toàn':<25} | {lr_probs[0]*100:5.1f}%{'':<19} | {rf_probs[0]*100:5.1f}%")
    print(f"{'Xác suất Có nguy cơ':<25} | {lr_probs[1]*100:5.1f}%{'':<19} | {rf_probs[1]*100:5.1f}%")
    print(f"{'Xác suất Lũ lớn (Lớp 2)':<25} | {lr_probs[2]*100:5.1f}%{'':<19} | {rf_probs[2]*100:5.1f}%")
    print("-" * 75)
    if lr_pred == rf_pred:
        print("-> ĐÁNH GIÁ: Cả 2 mô hình ĐỒNG THUẬN TUYỆT ĐỐI về kết quả cảnh báo!")
    else:
        print("-> ĐÁNH GIÁ: Có sự khác biệt giữa 2 mô hình (Mô hình Logistic Regression nhạy hơn để cứu người).")
    print("=" * 75)


def run_preset_scenarios(lr_model, rf_model):
    """Chạy thử 3 kịch bản chuẩn."""
    presets = {
        "1": {
            "name": "Mùa khô bình thường (Nắng ráo, dòng chảy thấp)",
            "data": {
                "rain_daily_mm": 0.0, "rain_max_hourly_mmh": 0.0, "rain_3d_accum_mm": 2.0, "rain_7d_accum_mm": 12.0,
                "water_level_cm": 60.0, "delta_water_level_cm": 1.0, "river_discharge_m3s": 220.0, "discharge_3d_mean_m3s": 235.0,
                "delta_discharge_m3s": -5.0
            }
        },
        "2": {
            "name": "Chuyển tiếp đợt mưa lớn (Có nguy cơ chớm ngập BĐ1)",
            "data": {
                "rain_daily_mm": 32.6, "rain_max_hourly_mmh": 4.4, "rain_3d_accum_mm": 36.3, "rain_7d_accum_mm": 70.2,
                "water_level_cm": 85.0, "delta_water_level_cm": -20.0, "river_discharge_m3s": 520.0, "discharge_3d_mean_m3s": 915.0,
                "delta_discharge_m3s": -150.0
            }
        },
        "3": {
            "name": "Bão lớn đổ bộ + Thủy điện xả lũ dồn dập (Lũ lịch sử trên BĐ2)",
            "data": {
                "rain_daily_mm": 140.0, "rain_max_hourly_mmh": 28.0, "rain_3d_accum_mm": 270.0, "rain_7d_accum_mm": 320.0,
                "water_level_cm": 280.0, "delta_water_level_cm": 95.0, "river_discharge_m3s": 3400.0, "discharge_3d_mean_m3s": 2200.0,
                "delta_discharge_m3s": 1600.0
            }
        }
    }

    for key, p in presets.items():
        print(f"\n>>> [KỊCH BẢN {key}]: {p['name']}")
        predict_single(lr_model, "Logistic Regression", p["data"])
        compare_both_models(lr_model, rf_model, p["data"], p["name"])


def run_historical_backtesting(lr_model, rf_model, n_samples: int = 5):
    """Kiểm tra đối chiếu ngẫu nhiên trên các ngày lịch sử thực tế."""
    if not DATASET_FILE.exists():
        print(f"Lỗi: Không tìm thấy {DATASET_FILE}")
        return
    df = pd.read_csv(DATASET_FILE)
    print("\n" + "=" * 75)
    print(f"KIỂM THỬ ĐỐI CHIẾU LỊCH SỬ TRÊN {n_samples} NGÀY QUAN TRẮC THỰC TẾ (BACKTESTING)")
    print("=" * 75)

    # Chọn cả ngày nắng và ngày lũ thực tế để xem khả năng dự báo
    flood_days = df[df["target_lead24h"] > 0]
    safe_days = df[df["target_lead24h"] == 0]

    sample_flood = flood_days.sample(min(len(flood_days), 3), random_state=42)
    sample_safe = safe_days.sample(min(len(safe_days), 2), random_state=42)
    test_sample = pd.concat([sample_flood, sample_safe]).sample(frac=1.0, random_state=42)

    for _, row in test_sample.iterrows():
        input_data = {col: float(row[col]) for col in FEATURE_COLS}
        true_label = int(row["target_lead24h"])
        obs_date = row["date"]

        pred_lr = int(lr_model.predict(pd.DataFrame([input_data])[FEATURE_COLS])[0])
        pred_rf = int(rf_model.predict(pd.DataFrame([input_data])[FEATURE_COLS])[0])

        status_lr = "ĐÚNG" if pred_lr == true_label else "LỆCH"
        status_rf = "ĐÚNG" if pred_rf == true_label else "LỆCH"

        print(f"-> Ngày {obs_date} | Thực tế ngày mai: Lớp {true_label} | AI Logistic: Lớp {pred_lr} [{status_lr}] | AI Random Forest: Lớp {pred_rf} [{status_rf}]")
        print(f"   (Mưa 3 ngày: {input_data['rain_3d_accum_mm']}mm | Nước Câu Lâu: {input_data['water_level_cm']}cm | GloFAS: {input_data['river_discharge_m3s']}m³/s)")
    print("=" * 75)


def main():
    parser = argparse.ArgumentParser(description="Công cụ Thử nghiệm Mô hình AI Cảnh báo Ngập Hội An")
    parser.add_argument("--scenario", type=str, choices=["1", "2", "3", "all", "backtest"], default="all",
                        help="Chọn kịch bản kiểm thử: 1, 2, 3, all (mặc định), hoặc backtest (kiểm tra lịch sử)")
    args = parser.parse_args()

    lr_model, rf_model = load_models()

    if args.scenario in ["1", "2", "3"]:
        presets = {
            "1": ("Mùa khô bình thường", {
                "rain_daily_mm": 0.0, "rain_max_hourly_mmh": 0.0, "rain_3d_accum_mm": 2.0, "rain_7d_accum_mm": 12.0,
                "water_level_cm": 60.0, "delta_water_level_cm": 1.0, "river_discharge_m3s": 220.0, "discharge_3d_mean_m3s": 235.0,
                "delta_discharge_m3s": -5.0
            }),
            "2": ("Chuyển tiếp đợt mưa lớn", {
                "rain_daily_mm": 32.6, "rain_max_hourly_mmh": 4.4, "rain_3d_accum_mm": 36.3, "rain_7d_accum_mm": 70.2,
                "water_level_cm": 85.0, "delta_water_level_cm": -20.0, "river_discharge_m3s": 520.0, "discharge_3d_mean_m3s": 915.0,
                "delta_discharge_m3s": -150.0
            }),
            "3": ("Bão lớn và Xả lũ lịch sử", {
                "rain_daily_mm": 140.0, "rain_max_hourly_mmh": 28.0, "rain_3d_accum_mm": 270.0, "rain_7d_accum_mm": 320.0,
                "water_level_cm": 280.0, "delta_water_level_cm": 95.0, "river_discharge_m3s": 3400.0, "discharge_3d_mean_m3s": 2200.0,
                "delta_discharge_m3s": 1600.0
            }),
        }
        title, data = presets[args.scenario]
        predict_single(lr_model, "Logistic Regression (Mô hình An toàn #1)", data)
        compare_both_models(lr_model, rf_model, data, title)

    elif args.scenario == "backtest":
        run_historical_backtesting(lr_model, rf_model, n_samples=5)

    else:  # all
        run_preset_scenarios(lr_model, rf_model)
        run_historical_backtesting(lr_model, rf_model, n_samples=5)


if __name__ == "__main__":
    main()
