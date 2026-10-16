# -*- coding: utf-8 -*-
"""
simulate_ai_demo.py
=============================================================================
Công cụ Giả lập Tương tác Demo Mô hình AI Cảnh báo Ngập lụt Hội An
(Dự án AI + IoT Trường THPT Trần Quý Cáp)

Mục đích:
  - Cho phép người dùng chạy thử nghiệm mô hình đã huấn luyện trong môi trường giả lập.
  - Cung cấp các kịch bản thực tế (Mùa cạn, Mưa lớn cục bộ, Bão lũ thượng nguồn).
  - Tích hợp chuẩn hóa dữ liệu đầu vào và xuất khuyến nghị hành động tương ứng với phần cứng.
"""

import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np
import joblib

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

MODEL_FILE = Path("models/model_lead24h_random_forest.joblib") if Path("models/model_lead24h_random_forest.joblib").exists() else Path("model_lead24h_rf.joblib")
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


def ensure_model_exists():
    """Tự động kiểm tra và huấn luyện mô hình nếu chưa có tệp serialize."""
    if MODEL_FILE.exists():
        return joblib.load(MODEL_FILE)

    print("-> Đang tự động huấn luyện và đóng gói mô hình Random Forest (24h Lead-time)...")
    if not DATASET_FILE.exists():
        raise FileNotFoundError(f"Không tìm thấy {DATASET_FILE}! Chạy analyze_and_prepare_dataset.py trước.")

    df = pd.read_csv(DATASET_FILE)
    X = df[FEATURE_COLS].fillna(0.0)
    y = df["target_lead24h"].astype(int)

    rf = RandomForestClassifier(
        n_estimators=100, max_depth=6, class_weight="balanced", random_state=42
    )
    rf.fit(X, y)
    joblib.dump(rf, MODEL_FILE)
    print(f"-> Đã lưu mô hình vào {MODEL_FILE}")
    return rf


def predict_and_explain(model, input_dict: dict, scenario_name: str = "Tùy chỉnh"):
    """Dự báo nguy cơ ngập và giải thích kết quả cho người xem."""
    input_df = pd.DataFrame([input_dict])[FEATURE_COLS]

    # Dự báo nhãn và xác suất
    pred_label = int(model.predict(input_df)[0])
    probs = model.predict_proba(input_df)[0]

    status_map = {
        0: ("AN TOÀN (DƯỚI BÁO ĐỘNG 1)", "XANH", "Tắt"),
        1: ("CÓ NGUY CƠ NGẬP CỤC BỘ (BĐ1 - BĐ2)", "VÀNG", "Tắt"),
        2: ("NGUY CƠ CAO / LŨ LỚN (TRÊN BÁO ĐỘNG 2)", "ĐỎ (NHẤP NHÁY)", "BẬT CÒI HÚ LIÊN TỤC"),
    }
    desc, led, buzzer = status_map[pred_label]

    print("\n" + "=" * 75)
    print(f"KẾT QUẢ DỰ BÁO AI GIẢ LẬP: [{scenario_name.upper()}]")
    print("=" * 75)
    print("1. THÔNG SỐ ĐẦU VÀO GIẢ LẬP:")
    print(f"   * Lượng mưa ngày / Mưa giờ cực đại : {input_dict['rain_daily_mm']:>6.1f} mm  | {input_dict['rain_max_hourly_mmh']:>5.1f} mm/h")
    print(f"   * Mưa tích lũy 3 ngày / 7 ngày     : {input_dict['rain_3d_accum_mm']:>6.1f} mm  | {input_dict['rain_7d_accum_mm']:>5.1f} mm")
    print(f"   * Mực nước đo được / Tốc độ dâng   : {input_dict['water_level_cm']:>6.1f} cm  | {input_dict['delta_water_level_cm']:>+5.1f} cm/ngày")
    print(f"   * Lưu lượng sông GloFAS / Biến thiên: {input_dict['river_discharge_m3s']:>6.1f} m³/s | {input_dict['delta_discharge_m3s']:>+5.1f} m³/s")

    print("\n2. DỰ BÁO NGUY CƠ CHO 24 GIỜ TIẾP THEO (T+1):")
    print(f"   * Cấp độ rủi ro : Lớp {pred_label} -> {desc}")
    print(f"   * Độ tin cậy    : An toàn: {probs[0]*100:5.1f}% | Có nguy cơ: {probs[1]*100:5.1f}% | Lũ nguy cơ cao: {probs[2]*100:5.1f}%")

    print("\n3. PHẢN HỒI THIẾT BỊ PHẦN CỨNG (IoT Wokwi):")
    print(f"   * Đèn tín hiệu LED : {led}")
    print(f"   * Còi báo động     : {buzzer}")

    print("\n4. HÀNH ĐỘNG KHUYẾN NGHỊ CHO TRƯỜNG THPT TRẦN QUÝ CÁP:")
    if pred_label == 0:
        print("   -> Hoạt động dạy học diễn ra bình thường.")
        print("   -> Duy trì chế độ quan trắc tự động định kỳ 15 phút/lần.")
    elif pred_label == 1:
        print("   -> Đội xung kích nhà trường kiểm tra hệ thống nạo vét cống rãnh quanh sân trường.")
        print("   -> Kê cao thiết bị tại các phòng học tầng 1 và phòng máy tính.")
        print("   -> Theo dõi chặt chẽ bản tin thủy văn Câu Lâu tiếp theo.")
    else:
        print("   -> [KHẨN CẤP] Báo cáo Ban Giám hiệu ra thông báo cho toàn trường NGHỈ HỌC vào ngày mai.")
        print("   -> Cắt cầu dao điện tổng tầng 1, sơ tán hồ sơ học sinh và máy tính lên tầng 2.")
        print("   -> Phối hợp với Ban Chỉ huy PCTT&TKCN phường Minh An / Cẩm Phô lập rào chắn cảnh báo ngập sâu.")
    print("=" * 75)


def run_interactive_demo():
    """Chạy kịch bản demo mẫu hoặc nhận tham số nhập tay."""
    model = ensure_model_exists()

    scenarios = {
        "1": {
            "name": "Mùa khô bình thường (Nắng ráo, dòng chảy thấp)",
            "data": {
                "rain_daily_mm": 0.0,
                "rain_max_hourly_mmh": 0.0,
                "rain_3d_accum_mm": 2.0,
                "rain_7d_accum_mm": 12.0,
                "water_level_cm": 60.0,
                "delta_water_level_cm": 1.0,
                "river_discharge_m3s": 220.0,
                "discharge_3d_mean_m3s": 235.0,
                "delta_discharge_m3s": -5.0,
            },
        },
        "2": {
            "name": "Chuyển tiếp đợt mưa lớn (Có nguy cơ chớm ngập BĐ1)",
            "data": {
                "rain_daily_mm": 32.6,
                "rain_max_hourly_mmh": 4.4,
                "rain_3d_accum_mm": 36.3,
                "rain_7d_accum_mm": 70.2,
                "water_level_cm": 85.0,
                "delta_water_level_cm": -20.0,
                "river_discharge_m3s": 520.0,
                "discharge_3d_mean_m3s": 915.0,
                "delta_discharge_m3s": -150.0,
            },
        },
        "3": {
            "name": "Bão đổ bộ + Thủy điện thượng nguồn xả lũ dồn dập (Lũ lớn lịch sử)",
            "data": {
                "rain_daily_mm": 140.0,
                "rain_max_hourly_mmh": 28.0,
                "rain_3d_accum_mm": 270.0,
                "rain_7d_accum_mm": 320.0,
                "water_level_cm": 280.0,
                "delta_water_level_cm": 95.0,
                "river_discharge_m3s": 3400.0,
                "discharge_3d_mean_m3s": 2200.0,
                "delta_discharge_m3s": 1600.0,
            },
        },
    }

    print("=" * 75)
    print("HỆ THỐNG GIẢ LẬP DEMO AI CẢNH BÁO SỚM NGẬP LỤT HỘI AN")
    print("=" * 75)
    print("Danh sách các kịch bản giả lập có sẵn:")
    print("  [1] Kịch bản 1: Mùa khô bình thường (Nắng ráo, dòng chảy thấp)")
    print("  [2] Kịch bản 2: Mưa dông cục bộ tại phố cổ (Ngập úng đô thị nhẹ)")
    print("  [3] Kịch bản 3: Bão lớn + Thượng nguồn xả lũ (Lũ sông báo động cấp 2 - 3)")
    print("  [ALL] Chạy tuần tự cả 3 kịch bản để so sánh")

    # Mặc định chạy cả 3 kịch bản để kiểm tra toàn diện
    for key, sc in scenarios.items():
        predict_and_explain(model, sc["data"], sc["name"])


if __name__ == "__main__":
    run_interactive_demo()
