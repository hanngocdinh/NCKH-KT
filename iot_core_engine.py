"""
iot_core_engine.py — IoT Core Engine cho hệ thống cảnh báo lũ lụt AI
THPT Trần Quý Cáp, Hội An

Quản lý:
- Load model AI đã train
- Nhận dữ liệu cảm biến, tính delta features
- Suy luận mức rủi ro (0=An toàn, 1=Cảnh báo, 2=Nguy hiểm cao)
- Lưu lịch sử đo vào JSON để tải lại khi restart
"""

import json
import os
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

MODEL_DIR = Path(__file__).parent / "models"
HISTORY_FILE = Path(__file__).parent / "iot_telemetry_history.json"
HISTORY_MAX = 50

# Thứ tự đặc trưng phải khớp với lúc train
FEATURE_NAMES = [
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

RISK_LABELS = {
    0: "An toàn",
    1: "Cảnh báo",
    2: "Nguy hiểm cao",
}

RISK_COLORS = {
    0: "green",
    1: "yellow",
    2: "red",
}

RISK_ACTIONS = {
    0: "Hệ thống bình thường. Tiếp tục theo dõi định kỳ.",
    1: "Chú ý theo dõi! Kiểm tra thiết bị và thông báo cho học sinh.",
    2: "⚠️ KHẨN CẤP! Kích hoạt ngay phương án sơ tán và cảnh báo toàn trường!",
}


class IoTCoreEngine:
    """Engine chính xử lý dữ liệu IoT và suy luận AI."""

    def __init__(self):
        self._model = None
        self._history: deque[dict] = deque(maxlen=HISTORY_MAX)
        self._load_model()
        self._load_history()

    # ------------------------------------------------------------------
    # Model
    # ------------------------------------------------------------------
    def _load_model(self):
        model_path = MODEL_DIR / "model_lead24h_logistic_regression.joblib"
        if not model_path.exists():
            raise FileNotFoundError(f"Không tìm thấy model tại: {model_path}")
        self._model = joblib.load(model_path)

    # ------------------------------------------------------------------
    # History persistence
    # ------------------------------------------------------------------
    def _load_history(self):
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data[-HISTORY_MAX:]:
                    self._history.append(item)
            except (json.JSONDecodeError, KeyError):
                self._history.clear()

    def _save_history(self):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(list(self._history), f, ensure_ascii=False, indent=2, default=str)

    # ------------------------------------------------------------------
    # Delta computation
    # ------------------------------------------------------------------
    def _compute_deltas(self, water_level_cm: float, river_discharge_m3s: float) -> tuple[float, float]:
        """Tính Δwater_level và Δdischarge so với điểm đo trước."""
        if len(self._history) > 0:
            prev = self._history[-1]
            delta_wl = water_level_cm - prev.get("water_level_cm", water_level_cm)
            delta_q = river_discharge_m3s - prev.get("river_discharge_m3s", river_discharge_m3s)
        else:
            delta_wl = 0.0
            delta_q = 0.0
        return delta_wl, delta_q

    def _compute_discharge_3d_mean(self, river_discharge_m3s: float) -> float:
        """Trung bình lưu lượng 3 ngày gần nhất (72 điểm nếu đo mỗi giờ, lấy tối đa 72 từ history)."""
        recent = list(self._history)[-71:]  # 71 điểm trước + điểm hiện tại = 72
        discharges = [r.get("river_discharge_m3s", river_discharge_m3s) for r in recent]
        discharges.append(river_discharge_m3s)
        return float(np.mean(discharges))

    # ------------------------------------------------------------------
    # Core inference
    # ------------------------------------------------------------------
    def infer(self, sensor_dict: dict[str, Any]) -> dict[str, Any]:
        """
        Nhận dict cảm biến thô, trả về dict kết quả suy luận.

        sensor_dict yêu cầu:
            rain_daily_mm, rain_max_hourly_mmh, rain_3d_accum_mm, rain_7d_accum_mm,
            water_level_cm, river_discharge_m3s
        (delta và discharge_3d_mean được tự động tính từ history)
        """
        water_level_cm = float(sensor_dict.get("water_level_cm", 0))
        river_discharge_m3s = float(sensor_dict.get("river_discharge_m3s", 0))

        delta_wl, delta_q = self._compute_deltas(water_level_cm, river_discharge_m3s)
        discharge_3d_mean = self._compute_discharge_3d_mean(river_discharge_m3s)

        # Ưu tiên giá trị truyền trực tiếp nếu có (ví dụ diễn tập dữ liệu lịch sử chuẩn)
        if "delta_water_level_cm" in sensor_dict:
            delta_wl = float(sensor_dict["delta_water_level_cm"])
        if "delta_discharge_m3s" in sensor_dict:
            delta_q = float(sensor_dict["delta_discharge_m3s"])
        if "discharge_3d_mean_m3s" in sensor_dict:
            discharge_3d_mean = float(sensor_dict["discharge_3d_mean_m3s"])

        features = {
            "rain_daily_mm": float(sensor_dict.get("rain_daily_mm", 0)),
            "rain_max_hourly_mmh": float(sensor_dict.get("rain_max_hourly_mmh", 0)),
            "rain_3d_accum_mm": float(sensor_dict.get("rain_3d_accum_mm", 0)),
            "rain_7d_accum_mm": float(sensor_dict.get("rain_7d_accum_mm", 0)),
            "water_level_cm": water_level_cm,
            "delta_water_level_cm": delta_wl,
            "river_discharge_m3s": river_discharge_m3s,
            "discharge_3d_mean_m3s": discharge_3d_mean,
            "delta_discharge_m3s": delta_q,
        }

        X = pd.DataFrame([features])[FEATURE_NAMES]
        risk_level = int(self._model.predict(X)[0])
        probs = self._model.predict_proba(X)[0].tolist()

        timestamp = datetime.now().isoformat()

        record = {
            "timestamp": timestamp,
            **features,
            "risk_level": risk_level,
            "prob_safe": probs[0],
            "prob_warning": probs[1],
            "prob_high_risk": probs[2],
        }
        self._history.append(record)
        self._save_history()

        return {
            "timestamp": timestamp,
            "risk_level": risk_level,
            "risk_label": RISK_LABELS[risk_level],
            "alert_color": RISK_COLORS[risk_level],
            "action": RISK_ACTIONS[risk_level],
            "probs": probs,
            "features": features,
        }

    # ------------------------------------------------------------------
    # History access
    # ------------------------------------------------------------------
    def get_history_df(self) -> pd.DataFrame:
        """Trả về DataFrame lịch sử đo."""
        if not self._history:
            return pd.DataFrame()
        return pd.DataFrame(list(self._history))

    def clear_history(self):
        self._history.clear()
        if HISTORY_FILE.exists():
            os.remove(HISTORY_FILE)
