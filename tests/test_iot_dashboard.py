"""
tests/test_iot_dashboard.py — Tests cho IoT Core Engine và Alert Notifier
THPT Trần Quý Cáp, Hội An
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Đảm bảo import từ thư mục gốc project
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from iot_core_engine import IoTCoreEngine, RISK_LABELS, FEATURE_NAMES
from alert_notifier import AlertNotifier


# ──────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────

@pytest.fixture
def engine(tmp_path, monkeypatch):
    """IoTCoreEngine với history file tạm để tránh ghi vào project."""
    monkeypatch.setattr("iot_core_engine.HISTORY_FILE", tmp_path / "test_history.json")
    return IoTCoreEngine()


@pytest.fixture
def scenario_safe():
    return {
        "rain_daily_mm": 0.0,
        "rain_max_hourly_mmh": 0.0,
        "rain_3d_accum_mm": 2.0,
        "rain_7d_accum_mm": 5.0,
        "water_level_cm": 60.0,
        "river_discharge_m3s": 220.0,
    }


@pytest.fixture
def scenario_warning():
    return {
        "rain_daily_mm": 32.6,
        "rain_max_hourly_mmh": 15.0,
        "rain_3d_accum_mm": 36.3,
        "rain_7d_accum_mm": 55.0,
        "water_level_cm": 85.0,
        "river_discharge_m3s": 520.0,
    }


@pytest.fixture
def scenario_flood():
    """
    Lấy một dòng thực tế lớp 2 từ dataset để đảm bảo model nhận diện đúng.
    Nếu dataset không có, fallback về giá trị synthetic cực đoan.
    """
    import pandas as pd
    csv_path = Path(__file__).parent.parent / "hoian_flood_ai_dataset_prepared.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        class2 = df[df["target_lead24h"] == 2]
        if not class2.empty:
            row = class2.iloc[0]
            return {
                "rain_daily_mm": float(row.get("rain_daily_mm", 140.0)),
                "rain_max_hourly_mmh": float(row.get("rain_max_hourly_mmh", 65.0)),
                "rain_3d_accum_mm": float(row.get("rain_3d_accum_mm", 270.0)),
                "rain_7d_accum_mm": float(row.get("rain_7d_accum_mm", 380.0)),
                "water_level_cm": float(row.get("water_level_cm", 320.0)),
                "river_discharge_m3s": float(row.get("river_discharge_m3s", 5000.0)),
                "_delta_water_level_cm": float(row.get("delta_water_level_cm", 50.0)),
                "_discharge_3d_mean_m3s": float(row.get("discharge_3d_mean_m3s", 3000.0)),
                "_delta_discharge_m3s": float(row.get("delta_discharge_m3s", 1000.0)),
            }
    # Fallback
    return {
        "rain_daily_mm": 140.0,
        "rain_max_hourly_mmh": 65.0,
        "rain_3d_accum_mm": 270.0,
        "rain_7d_accum_mm": 380.0,
        "water_level_cm": 320.0,
        "river_discharge_m3s": 5000.0,
    }


# ──────────────────────────────────────────────────────────
# IoTCoreEngine — inference structure
# ──────────────────────────────────────────────────────────

class TestIoTCoreEngineInference:
    def test_infer_returns_required_keys(self, engine, scenario_safe):
        result = engine.infer(scenario_safe)
        required = {"timestamp", "risk_level", "risk_label", "alert_color", "action", "probs", "features"}
        assert required.issubset(result.keys()), f"Thiếu keys: {required - result.keys()}"

    def test_infer_risk_level_is_valid_int(self, engine, scenario_safe):
        result = engine.infer(scenario_safe)
        assert result["risk_level"] in (0, 1, 2)

    def test_infer_probs_sum_to_one(self, engine, scenario_safe):
        result = engine.infer(scenario_safe)
        assert abs(sum(result["probs"]) - 1.0) < 1e-5

    def test_infer_probs_has_3_elements(self, engine, scenario_flood):
        result = engine.infer(scenario_flood)
        assert len(result["probs"]) == 3

    def test_infer_risk_label_matches_level(self, engine, scenario_warning):
        result = engine.infer(scenario_warning)
        assert result["risk_label"] == RISK_LABELS[result["risk_level"]]

    def test_infer_alert_color_is_valid(self, engine, scenario_flood):
        result = engine.infer(scenario_flood)
        assert result["alert_color"] in ("green", "yellow", "red")

    def test_infer_features_contains_all_feature_names(self, engine, scenario_safe):
        result = engine.infer(scenario_safe)
        for feat in FEATURE_NAMES:
            assert feat in result["features"], f"Thiếu feature: {feat}"

    def test_scenario_flood_detects_high_risk(self, engine, tmp_path, monkeypatch):
        """Kịch bản lũ nặng phải trả về risk_level=2 — dùng dòng thực tế từ dataset."""
        import pandas as pd
        monkeypatch.setattr("iot_core_engine.HISTORY_FILE", tmp_path / "h.json")
        csv_path = Path(__file__).parent.parent / "hoian_flood_ai_dataset_prepared.csv"
        if not csv_path.exists():
            pytest.skip("Dataset không có — bỏ qua test này")
        df = pd.read_csv(csv_path)
        class2 = df[df["target_lead24h"] == 2]
        if class2.empty:
            pytest.skip("Không có dữ liệu class 2 trong dataset")
        # Prime history với dòng trước đó (nếu có)
        row_idx = class2.index[0]
        if row_idx > 0:
            prev_row = df.loc[row_idx - 1]
            engine.infer({
                "rain_daily_mm": float(prev_row.get("rain_daily_mm", 0)),
                "rain_max_hourly_mmh": float(prev_row.get("rain_max_hourly_mmh", 0)),
                "rain_3d_accum_mm": float(prev_row.get("rain_3d_accum_mm", 0)),
                "rain_7d_accum_mm": float(prev_row.get("rain_7d_accum_mm", 0)),
                "water_level_cm": float(prev_row.get("water_level_cm", 0)),
                "river_discharge_m3s": float(prev_row.get("river_discharge_m3s", 0)),
            })
        flood_row = class2.iloc[0]
        sensor = {
            "rain_daily_mm": float(flood_row.get("rain_daily_mm", 140.0)),
            "rain_max_hourly_mmh": float(flood_row.get("rain_max_hourly_mmh", 65.0)),
            "rain_3d_accum_mm": float(flood_row.get("rain_3d_accum_mm", 270.0)),
            "rain_7d_accum_mm": float(flood_row.get("rain_7d_accum_mm", 380.0)),
            "water_level_cm": float(flood_row.get("water_level_cm", 320.0)),
            "river_discharge_m3s": float(flood_row.get("river_discharge_m3s", 5000.0)),
        }
        result = engine.infer(sensor)
        assert result["risk_level"] == 2, (
            f"Model phải nhận diện kịch bản lũ là nguy hiểm (level 2), "
            f"nhưng trả về {result['risk_level']} — Probs: {result['probs']}"
        )

    def test_timestamp_is_iso_format(self, engine, scenario_safe):
        result = engine.infer(scenario_safe)
        # Kiểm tra parse được
        datetime.fromisoformat(result["timestamp"])


# ──────────────────────────────────────────────────────────
# IoTCoreEngine — delta computation
# ──────────────────────────────────────────────────────────

class TestDeltaComputation:
    def test_first_inference_delta_is_zero(self, engine, scenario_safe):
        result = engine.infer(scenario_safe)
        assert result["features"]["delta_water_level_cm"] == 0.0
        assert result["features"]["delta_discharge_m3s"] == 0.0

    def test_second_inference_computes_delta(self, engine):
        sensor1 = {"water_level_cm": 100.0, "river_discharge_m3s": 500.0}
        sensor2 = {"water_level_cm": 130.0, "river_discharge_m3s": 650.0}
        engine.infer(sensor1)
        result2 = engine.infer(sensor2)
        assert result2["features"]["delta_water_level_cm"] == pytest.approx(30.0)
        assert result2["features"]["delta_discharge_m3s"] == pytest.approx(150.0)


# ──────────────────────────────────────────────────────────
# IoTCoreEngine — history
# ──────────────────────────────────────────────────────────

class TestHistory:
    def test_history_grows_after_infer(self, engine, scenario_safe):
        for _ in range(3):
            engine.infer(scenario_safe)
        df = engine.get_history_df()
        assert len(df) == 3

    def test_history_df_has_expected_columns(self, engine, scenario_safe):
        engine.infer(scenario_safe)
        df = engine.get_history_df()
        for col in ["water_level_cm", "risk_level", "timestamp"]:
            assert col in df.columns

    def test_clear_history_empties_records(self, engine, scenario_safe):
        engine.infer(scenario_safe)
        engine.clear_history()
        df = engine.get_history_df()
        assert df.empty

    def test_history_persists_to_json(self, engine, scenario_safe, tmp_path):
        history_path = tmp_path / "test_history.json"
        import iot_core_engine
        original = iot_core_engine.HISTORY_FILE
        iot_core_engine.HISTORY_FILE = history_path
        try:
            engine.infer(scenario_safe)
            assert history_path.exists()
            with open(history_path) as f:
                data = json.load(f)
            assert len(data) >= 1
        finally:
            iot_core_engine.HISTORY_FILE = original


# ──────────────────────────────────────────────────────────
# AlertNotifier — cooldown
# ──────────────────────────────────────────────────────────

class TestAlertNotifier:
    @pytest.fixture
    def notifier(self, tmp_path, monkeypatch):
        monkeypatch.setattr("alert_notifier.ALERT_CONFIG_FILE", tmp_path / "config_alerts.json")
        return AlertNotifier()

    def test_cooldown_blocks_duplicate_alert(self, notifier):
        """Lần 2 gửi cùng mức risk trong 15 phút phải bị chặn."""
        notifier._token = "fake_token"
        notifier._chat_id = "fake_chat"
        # Đặt timestamp gần đây cho level 2
        notifier._last_alert_times[2] = datetime.now()
        result = {"risk_level": 2, "features": {}, "probs": [0, 0, 1], "action": "", "timestamp": datetime.now().isoformat()}
        out = notifier.send_telegram(result)
        assert out["skipped"] is True

    def test_cooldown_allows_alert_after_expiry(self, notifier):
        """Sau khi cooldown hết hạn, phải cho phép gửi."""
        notifier._token = "fake_token"
        notifier._chat_id = "fake_chat"
        # Đặt timestamp cũ hơn 15 phút
        notifier._last_alert_times[1] = datetime.now() - timedelta(minutes=20)
        result = {"risk_level": 1, "features": {"water_level_cm": 220, "rain_daily_mm": 30, "river_discharge_m3s": 800, "delta_water_level_cm": 5}, "probs": [0.1, 0.7, 0.2], "action": "test", "timestamp": datetime.now().isoformat()}
        with patch("alert_notifier.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp
            out = notifier.send_telegram(result)
        assert out["ok"] is True
        assert out["skipped"] is False

    def test_send_without_config_returns_error(self, notifier):
        """Chưa cấu hình token → trả về lỗi rõ ràng."""
        result = {"risk_level": 2, "features": {}, "probs": [0, 0, 1], "action": "", "timestamp": datetime.now().isoformat()}
        out = notifier.send_telegram(result)
        assert out["ok"] is False
        assert "Token" in out["error"] or "Chat ID" in out["error"]

    def test_dispatch_skips_safe_level(self, notifier):
        """Mức an toàn (level 0) không gửi cảnh báo."""
        result = {"risk_level": 0, "features": {}, "probs": [1, 0, 0], "action": "", "timestamp": datetime.now().isoformat()}
        out = notifier.dispatch(result)
        assert out["skipped"] is True

    def test_save_and_reload_config(self, tmp_path, monkeypatch):
        """Lưu config và đọc lại phải khớp."""
        config_path = tmp_path / "config_alerts.json"
        monkeypatch.setattr("alert_notifier.ALERT_CONFIG_FILE", config_path)
        from alert_notifier import save_config, _load_config
        save_config("mytoken123", "mychat456")
        cfg = _load_config()
        assert cfg["telegram_token"] == "mytoken123"
        assert cfg["telegram_chat_id"] == "mychat456"
