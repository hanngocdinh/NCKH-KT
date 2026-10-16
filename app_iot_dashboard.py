"""
app_iot_dashboard.py — Dashboard giám sát lũ lụt AI & Giả lập IoT Chuyên sâu
THPT Trần Quý Cáp, Hội An

Gồm 3 tab:
  Tab 1: 🏠 Bảng Giám sát — realtime monitoring & alert status
  Tab 2: 🛠️ Giả lập IoT    — Interactive simulation, in-place live replay & physics generator
  Tab 3: ⚙️ Cài đặt       — Telegram Bot configuration & system reset

Chạy: streamlit run app_iot_dashboard.py
"""

import json
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from alert_notifier import AlertNotifier, save_config
from iot_core_engine import IoTCoreEngine

# ──────────────────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🌊 Hệ thống Cảnh báo Lũ lụt AI — Hội An",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────
# Session-state init
# ──────────────────────────────────────────────────────────
def _init_state():
    if "engine" not in st.session_state:
        st.session_state.engine = IoTCoreEngine()
    if "notifier" not in st.session_state:
        st.session_state.notifier = AlertNotifier()
    if "last_result" not in st.session_state:
        st.session_state.last_result = None
    if "alert_log" not in st.session_state:
        st.session_state.alert_log = []
    # Preset buffer
    if "sim_params" not in st.session_state:
        st.session_state.sim_params = {
            "rain_daily_mm": 0.0,
            "rain_max_hourly_mmh": 0.0,
            "rain_3d_accum_mm": 2.0,
            "rain_7d_accum_mm": 5.0,
            "water_level_cm": 60.0,
            "river_discharge_m3s": 220.0,
        }

_init_state()

engine: IoTCoreEngine = st.session_state.engine
notifier: AlertNotifier = st.session_state.notifier

# ──────────────────────────────────────────────────────────
# Constants & Colors
# ──────────────────────────────────────────────────────────
RISK_CSS = {
    0: ("🟢 AN TOÀN", "#1e7e34", "#d4edda", "Hệ thống bình thường. Tiếp tục theo dõi định kỳ."),
    1: ("🟡 CẢNH BÁO", "#856404", "#fff3cd", "Chú ý theo dõi! Kiểm tra thiết bị và chuẩn bị phương án ứng phó."),
    2: ("🔴 NGUY HIỂM CAO", "#721c24", "#f8d7da", "⚠️ KHẨN CẤP! Mực nước chạm ngưỡng nguy hiểm, kích hoạt sơ tán học sinh!"),
}

BĐ1_CM = 200  # Báo động 1 (Cầu Lâu)
BĐ2_CM = 300  # Báo động 2 (Cầu Lâu)

# ──────────────────────────────────────────────────────────
# Load historical storm data for auto-play
# ──────────────────────────────────────────────────────────
@st.cache_data
def _load_storm_data() -> pd.DataFrame:
    csv_path = Path(__file__).parent / "hoian_flood_ai_dataset_prepared.csv"
    if not csv_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(csv_path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df

DATASET_ALL = _load_storm_data()

# ──────────────────────────────────────────────────────────
# Preset scenarios
# ──────────────────────────────────────────────────────────
PRESETS = {
    "☀️ Mùa cạn (An toàn)": {
        "rain_daily_mm": 0.0,
        "rain_max_hourly_mmh": 0.0,
        "rain_3d_accum_mm": 2.0,
        "rain_7d_accum_mm": 5.0,
        "water_level_cm": 60.0,
        "river_discharge_m3s": 220.0,
        "delta_water_level_cm": 0.0,
        "delta_discharge_m3s": 0.0,
    },
    "🌧️ Mưa lớn đầu mùa (Cảnh báo sớm)": {
        "rain_daily_mm": 45.0,
        "rain_max_hourly_mmh": 18.0,
        "rain_3d_accum_mm": 60.0,
        "rain_7d_accum_mm": 95.0,
        "water_level_cm": 140.0,
        "river_discharge_m3s": 850.0,
        "delta_water_level_cm": 15.0,
        "delta_discharge_m3s": 250.0,
    },
    "⚠️ Chạm Báo động 1 (200cm)": {
        "rain_daily_mm": 75.0,
        "rain_max_hourly_mmh": 32.0,
        "rain_3d_accum_mm": 120.0,
        "rain_7d_accum_mm": 180.0,
        "water_level_cm": 210.0,
        "river_discharge_m3s": 1450.0,
        "delta_water_level_cm": 35.0,
        "delta_discharge_m3s": 500.0,
    },
    "🌊 Đỉnh lũ lịch sử (Vượt BĐ2)": {
        "rain_daily_mm": 170.0,
        "rain_max_hourly_mmh": 68.0,
        "rain_3d_accum_mm": 320.0,
        "rain_7d_accum_mm": 450.0,
        "water_level_cm": 360.0,
        "river_discharge_m3s": 5200.0,
        "delta_water_level_cm": 65.0,
        "delta_discharge_m3s": 1800.0,
    },
    "⚡ Thủy điện xả lũ đột biến": {
        "rain_daily_mm": 25.0,
        "rain_max_hourly_mmh": 10.0,
        "rain_3d_accum_mm": 80.0,
        "rain_7d_accum_mm": 150.0,
        "water_level_cm": 260.0,
        "river_discharge_m3s": 4800.0,
        "delta_water_level_cm": 80.0,
        "delta_discharge_m3s": 2800.0,
    },
}

# ──────────────────────────────────────────────────────────
# UI Components & Plotly Chart Builders
# ──────────────────────────────────────────────────────────
def _render_alert_banner(risk_level: int):
    label, fg, bg, desc = RISK_CSS.get(risk_level, RISK_CSS[0])
    st.markdown(
        f"""<div style="background:{bg};color:{fg};padding:14px;border-radius:10px;
            text-align:center;font-size:1.4rem;font-weight:bold;margin-bottom:12px;border:1px solid {fg}44;">
            {label} &nbsp;—&nbsp; <span style='font-size:1.05rem;font-weight:normal;'>{desc}</span>
        </div>""",
        unsafe_allow_html=True,
    )


def _gauge_water_level(water_level_cm: float) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=water_level_cm,
            domain={"x": [0, 1], "y": [0, 1]},
            title={"text": "Mực nước trạm Cầu Lâu (cm)", "font": {"size": 15, "color": "#1a5276"}},
            number={"suffix": " cm", "font": {"size": 24, "color": "#2c3e50"}},
            gauge={
                "axis": {"range": [0, 500], "tickwidth": 1, "tickcolor": "#7f8c8d"},
                "bar": {"color": "#2980b9", "thickness": 0.3},
                "bgcolor": "white",
                "borderwidth": 1,
                "bordercolor": "#bdc3c7",
                "steps": [
                    {"range": [0, BĐ1_CM], "color": "#d4edda"},
                    {"range": [BĐ1_CM, BĐ2_CM], "color": "#fff3cd"},
                    {"range": [BĐ2_CM, 500], "color": "#f8d7da"},
                ],
                "threshold": {
                    "line": {"color": "#c0392b", "width": 4},
                    "thickness": 0.8,
                    "value": BĐ2_CM,
                },
            },
        )
    )
    fig.update_layout(margin=dict(l=20, r=20, t=35, b=20), height=230)
    return fig


def _prob_bar_chart(probs: list[float]) -> go.Figure:
    labels = ["An toàn (<BĐ1)", "Cảnh báo (BĐ1-2)", "Nguy hiểm (≥BĐ2)"]
    colors = ["#28a745", "#ffc107", "#dc3545"]
    vals = [p * 100 for p in probs]
    fig = go.Figure(
        go.Bar(
            x=labels,
            y=vals,
            marker_color=colors,
            text=[f"{v:.1f}%" for v in vals],
            textposition="outside",
            width=0.45,
        )
    )
    fig.update_layout(
        yaxis=dict(range=[0, 118], title="Xác suất (%)"),
        margin=dict(l=20, r=20, t=35, b=20),
        height=230,
        title="Dự báo AI rủi ro ngập lụt 24h tới",
    )
    return fig


def _history_line_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not df.empty and "water_level_cm" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["water_level_cm"],
                mode="lines+markers",
                name="Mực nước (cm)",
                line=dict(color="#2980b9", width=2.5),
                marker=dict(size=6, color="#1b4f72"),
            )
        )
        if "river_discharge_m3s" in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df["timestamp"],
                    y=df["river_discharge_m3s"] / 10.0,
                    mode="lines",
                    name="GloFAS / 10 (m³/s)",
                    line=dict(color="#e67e22", width=1.5, dash="dot"),
                    yaxis="y",
                )
            )

    fig.add_hline(y=BĐ1_CM, line_dash="dash", line_color="#f39c12", annotation_text="BĐ1 (200cm)")
    fig.add_hline(y=BĐ2_CM, line_dash="dash", line_color="#c0392b", annotation_text="BĐ2 (300cm)")
    fig.update_layout(
        title="Lịch sử mực nước & Lưu lượng thượng nguồn",
        xaxis_title="Thời gian cập nhật",
        yaxis_title="Mực nước Cầu Lâu (cm)",
        height=320,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=45, b=20),
    )
    return fig


def _run_inference(sensor_dict: dict) -> dict:
    result = engine.infer(sensor_dict)
    log_entry = {
        "Thời gian": result["timestamp"][:19].replace("T", " "),
        "Mực nước (cm)": sensor_dict.get("water_level_cm", 0),
        "Mưa ngày (mm)": sensor_dict.get("rain_daily_mm", 0),
        "Lưu lượng (m³/s)": sensor_dict.get("river_discharge_m3s", 0),
        "Mức cảnh báo": result["risk_label"],
    }
    st.session_state.alert_log.insert(0, log_entry)
    st.session_state.alert_log = st.session_state.alert_log[:100]
    st.session_state.last_result = result
    notifier.dispatch(result)
    return result


# ══════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════
st.markdown(
    """
    <div style='background: linear-gradient(135deg, #1b4f72, #2980b9); padding: 18px; border-radius: 12px; color: white; margin-bottom: 15px;'>
        <h2 style='margin:0; text-align:center;'>🌊 HỆ THỐNG GIÁM SÁT & CẢNH BÁO LŨ LỤT AI</h2>
        <p style='margin:4px 0 0 0; text-align:center; font-size:1.05rem; opacity:0.9;'>
            Trường THPT Trần Quý Cáp — Hội An &nbsp;|&nbsp; Dự báo rủi ro ngập trước 24 giờ &nbsp;|&nbsp; Machine Learning 100% Recall
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

tab1, tab2, tab3 = st.tabs(["🏠 Bảng Giám sát", "🛠️ Giả lập IoT & Diễn tập", "⚙️ Cài đặt Cảnh báo"])


# ══════════════════════════════════════════════════════════
# TAB 1: BẢNG GIÁM SÁT
# ══════════════════════════════════════════════════════════
with tab1:
    res = st.session_state.last_result

    if res is None:
        st.info("📡 Chưa nhận dữ liệu đo nào. Vui lòng chuyển sang **🛠️ Giả lập IoT & Diễn tập** để kích hoạt dữ liệu giả lập hoặc chạy diễn tập.")
    else:
        _render_alert_banner(res["risk_level"])

        f = res["features"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "🌊 Mực nước Cầu Lâu",
            f"{f['water_level_cm']:.0f} cm",
            delta=f"{f['delta_water_level_cm']:+.1f} cm",
            help="Mực nước quan trắc tại trạm Thủy văn Cầu Lâu (Hội An)",
        )
        c2.metric(
            "🌧️ Lượng mưa ngày",
            f"{f['rain_daily_mm']:.1f} mm",
            delta=f"Cực đại: {f['rain_max_hourly_mmh']:.1f} mm/h",
            help="Tổng lượng mưa đo được trong ngày và cường độ giờ cao nhất",
        )
        c3.metric(
            "🏞️ Lưu lượng xả GloFAS",
            f"{f['river_discharge_m3s']:.0f} m³/s",
            delta=f"{f['delta_discharge_m3s']:+.0f} m³/s",
            help="Lưu lượng dự báo vệ tinh Copernicus GloFAS lưu vực sông Thu Bồn",
        )
        c4.metric(
            "🔮 Mức rủi ro 24h",
            res["risk_label"],
            delta=f"P(lũ): {res['probs'][2]*100:.1f}%",
            delta_color="inverse" if res["risk_level"] == 2 else "normal",
        )

        st.caption(f"⏱️ Lần phân tích gần nhất: `{res['timestamp'][:19].replace('T', ' ')}`")

        col_g, col_p = st.columns([1, 1])
        with col_g:
            st.plotly_chart(_gauge_water_level(f["water_level_cm"]), use_container_width=True)
        with col_p:
            st.plotly_chart(_prob_bar_chart(res["probs"]), use_container_width=True)

        history_df = engine.get_history_df()
        if not history_df.empty:
            st.plotly_chart(_history_line_chart(history_df), use_container_width=True)

    if st.session_state.alert_log:
        st.subheader("📋 Nhật ký quan trắc & cảnh báo gần nhất")
        log_df = pd.DataFrame(st.session_state.alert_log)
        st.dataframe(log_df, use_container_width=True, hide_index=True)

    st.button("🔄 Làm mới dữ liệu", on_click=lambda: None)


# ══════════════════════════════════════════════════════════
# TAB 2: GIẢ LẬP IOT & DIỄN TẬP BÃO (SIÊU MƯỢT)
# ══════════════════════════════════════════════════════════
with tab2:
    st.subheader("🛠️ Trung tâm Giả lập Thiết bị IoT & Kịch bản Khẩn cấp")

    # ──────────────────────────────────────────────────────
    # Chế độ A: Kịch bản mẫu nhanh
    # ──────────────────────────────────────────────────────
    st.markdown("##### ⚡ 1. Nạp kịch bản mẫu nhanh:")
    preset_cols = st.columns(len(PRESETS))
    for idx, (p_name, p_vals) in enumerate(PRESETS.items()):
        if preset_cols[idx].button(p_name, use_container_width=True):
            st.session_state.sim_params = p_vals.copy()
            _run_inference(p_vals)
            st.rerun()

    cur_p = st.session_state.sim_params

    # ──────────────────────────────────────────────────────
    # Chế độ B: Điều chỉnh thông số cảm biến thủ công
    # ──────────────────────────────────────────────────────
    st.markdown("##### 🎛️ 2. Tinh chỉnh thông số cảm biến ảo (Fine-tune):")
    col_input1, col_input2, col_input3 = st.columns(3)

    with col_input1:
        rain_daily = st.slider("🌧️ Mưa ngày (mm)", 0.0, 300.0, float(cur_p.get("rain_daily_mm", 0.0)), 0.5)
        rain_max_h = st.slider("⛈️ Mưa cực đại giờ (mm/h)", 0.0, 150.0, float(cur_p.get("rain_max_hourly_mmh", 0.0)), 0.5)

    with col_input2:
        rain_3d = st.slider("📅 Mưa tích lũy 3 ngày (mm)", 0.0, 600.0, float(cur_p.get("rain_3d_accum_mm", 0.0)), 1.0)
        rain_7d = st.slider("📅 Mưa tích lũy 7 ngày (mm)", 0.0, 900.0, float(cur_p.get("rain_7d_accum_mm", 0.0)), 1.0)

    with col_input3:
        water_level = st.slider("🌊 Mực nước trạm Cầu Lâu (cm)", 0.0, 500.0, float(cur_p.get("water_level_cm", 60.0)), 1.0)
        discharge = st.slider("🏞️ Lưu lượng xả thượng nguồn (m³/s)", 0.0, 8000.0, float(cur_p.get("river_discharge_m3s", 220.0)), 10.0)

    # Hiệu ứng ngẫu nhiên (nhiễu cảm biến)
    with st.expander("🎲 Cấu hình nâng cao: Nhiễu cảm biến & Delta cưỡng bức"):
        col_adv1, col_adv2 = st.columns(2)
        with col_adv1:
            sensor_noise = st.checkbox("Thêm nhiễu ngẫu nhiên Gauss (±2% cảm biến)", value=False)
        with col_adv2:
            custom_deltas = st.checkbox("Ghi đè thủ công $\Delta$ Water level & $\Delta$ Discharge", value=False)
            delta_wl_val = 0.0
            delta_q_val = 0.0
            if custom_deltas:
                delta_wl_val = st.number_input("Δ Mực nước (cm)", value=10.0, step=1.0)
                delta_q_val = st.number_input("Δ Lưu lượng (m³/s)", value=200.0, step=10.0)

    btn_c1, btn_c2 = st.columns([2, 1])
    with btn_c1:
        if st.button("📡 Gửi tín hiệu giả lập → Phân tích AI", type="primary", use_container_width=True):
            input_dict = {
                "rain_daily_mm": rain_daily * (1 + random.uniform(-0.02, 0.02) if sensor_noise else 1),
                "rain_max_hourly_mmh": rain_max_h,
                "rain_3d_accum_mm": rain_3d,
                "rain_7d_accum_mm": rain_7d,
                "water_level_cm": water_level * (1 + random.uniform(-0.01, 0.01) if sensor_noise else 1),
                "river_discharge_m3s": discharge * (1 + random.uniform(-0.02, 0.02) if sensor_noise else 1),
            }
            if custom_deltas:
                input_dict["delta_water_level_cm"] = delta_wl_val
                input_dict["delta_discharge_m3s"] = delta_q_val

            st.session_state.sim_params = input_dict.copy()
            _run_inference(input_dict)
            st.rerun()

    with btn_c2:
        if st.button("🔄 Tạo chuỗi ngẫu nhiên (5 điểm)", use_container_width=True):
            base_w = water_level
            base_q = discharge
            for i in range(5):
                base_w = max(40.0, min(480.0, base_w + random.uniform(-15.0, 30.0)))
                base_q = max(100.0, min(7500.0, base_q + random.uniform(-100.0, 400.0)))
                pt = {
                    "rain_daily_mm": rain_daily,
                    "rain_max_hourly_mmh": rain_max_h,
                    "rain_3d_accum_mm": rain_3d,
                    "rain_7d_accum_mm": rain_7d,
                    "water_level_cm": base_w,
                    "river_discharge_m3s": base_q,
                }
                _run_inference(pt)
            st.success("✅ Đã sinh 5 điểm đo liên tiếp vào bộ đệm!")
            st.rerun()

    # ──────────────────────────────────────────────────────
    # Chế độ C: Diễn tập bão lịch sử (Replay in-place)
    # ──────────────────────────────────────────────────────
    st.divider()
    st.markdown("##### ⏯️ 3. Diễn tập sự kiện bão lịch sử thực tế (Replay siêu mượt không lag):")

    if DATASET_ALL.empty:
        st.warning("⚠️ Không tìm thấy file dữ liệu `hoian_flood_ai_dataset_prepared.csv`.")
    else:
        # Danh sách các đợt bão lịch sử tiêu biểu
        EVENT_PRESETS = {
            "🌊 Đợt bão tháng 11/2024 (Đỉnh lũ 480cm trên BĐ2)": ("2024-11-01", "2024-11-16"),
            "⛈️ Đợt bão tháng 10/2024 (Lũ đầu mùa, ngập báo động 1-2)": ("2024-10-18", "2024-10-31"),
            "🌊 Đợt lũ tháng 12/2024 (Xả lũ hồ thượng nguồn)": ("2024-12-10", "2024-12-20"),
            "☀️ Giai đoạn mùa khô yên tĩnh (Tháng 03/2025)": ("2025-03-01", "2025-03-15"),
        }

        col_sel, col_spd = st.columns([2, 1])
        with col_sel:
            selected_event = st.selectbox("Chọn sự kiện lịch sử để diễn tập:", list(EVENT_PRESETS.keys()))
        with col_spd:
            speed_opt = st.select_slider(
                "Tốc độ phát:",
                options=["Chậm (1.0s)", "Vừa (0.4s)", "Nhanh (0.15s)", "Tức thì (0s)"],
                value="Vừa (0.4s)",
            )
            spd_map = {"Chậm (1.0s)": 1.0, "Vừa (0.4s)": 0.4, "Nhanh (0.15s)": 0.15, "Tức thì (0s)": 0.0}
            delay_sec = spd_map[speed_opt]

        start_d, end_d = EVENT_PRESETS[selected_event]
        event_df = DATASET_ALL[(DATASET_ALL["date"] >= start_d) & (DATASET_ALL["date"] <= end_d)].copy()

        st.caption(f"📌 Sự kiện có **{len(event_df)}** mốc ngày quan trắc từ `{start_d}` đến `{end_d}`.")

        btn_run_sim, btn_clear = st.columns(2)
        run_replay = btn_run_sim.button("🚀 Bắt đầu diễn tập Live Replay", type="primary", use_container_width=True)
        clear_pressed = btn_clear.button("⏹️ Xóa bộ đệm & Dừng", use_container_width=True)

        if clear_pressed:
            engine.clear_history()
            st.session_state.last_result = None
            st.session_state.alert_log = []
            st.success("Đã reset bộ nhớ.")
            st.rerun()

        if run_replay:
            # Khởi tạo container động để cập nhật mượt mà tại chỗ (in-place)
            live_status = st.empty()
            live_prog = st.empty()
            live_metrics = st.empty()
            live_charts = st.empty()

            for step_idx, (_, row) in enumerate(event_df.iterrows()):
                sensor_data = {
                    "rain_daily_mm": float(row.get("rain_daily_mm", 0.0)),
                    "rain_max_hourly_mmh": float(row.get("rain_max_hourly_mmh", 0.0)),
                    "rain_3d_accum_mm": float(row.get("rain_3d_accum_mm", 0.0)),
                    "rain_7d_accum_mm": float(row.get("rain_7d_accum_mm", 0.0)),
                    "water_level_cm": float(row.get("water_level_cm", 60.0)),
                    "river_discharge_m3s": float(row.get("river_discharge_m3s", 220.0)),
                    "delta_water_level_cm": float(row.get("delta_water_level_cm", 0.0)),
                    "delta_discharge_m3s": float(row.get("delta_discharge_m3s", 0.0)),
                    "discharge_3d_mean_m3s": float(row.get("discharge_3d_mean_m3s", 220.0)),
                }

                res = _run_inference(sensor_data)
                date_label = str(row["date"])[:10]

                # Render thanh tiến trình
                prog_pct = (step_idx + 1) / len(event_df)
                live_prog.progress(prog_pct, text=f"Đang diễn tập ngày {step_idx+1}/{len(event_df)}: {date_label}")

                # Render banner
                label, fg, bg, desc = RISK_CSS[res["risk_level"]]
                live_status.markdown(
                    f"""<div style="background:{bg};color:{fg};padding:12px;border-radius:8px;
                        text-align:center;font-size:1.3rem;font-weight:bold;margin-bottom:8px;">
                        📅 {date_label} &nbsp;|&nbsp; {label} &nbsp;—&nbsp; {desc}
                    </div>""",
                    unsafe_allow_html=True,
                )

                # Render 4 metrics
                with live_metrics.container():
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("🌊 Mực nước", f"{sensor_data['water_level_cm']:.0f} cm", f"{sensor_data['delta_water_level_cm']:+.1f} cm")
                    m2.metric("🌧️ Mưa ngày", f"{sensor_data['rain_daily_mm']:.1f} mm")
                    m3.metric("🏞️ GloFAS", f"{sensor_data['river_discharge_m3s']:.0f} m³/s")
                    m4.metric("🔮 Cảnh báo AI", res["risk_label"], f"P(Nguy hiểm) = {res['probs'][2]*100:.1f}%")

                # Render Plotly visual
                with live_charts.container():
                    cg, cp = st.columns(2)
                    with cg:
                        st.plotly_chart(_gauge_water_level(sensor_data["water_level_cm"]), use_container_width=True, key=f"g_{step_idx}")
                    with cp:
                        st.plotly_chart(_prob_bar_chart(res["probs"]), use_container_width=True, key=f"p_{step_idx}")

                if delay_sec > 0:
                    time.sleep(delay_sec)

            st.success("🎉 Hoàn tất toàn bộ chuỗi diễn tập bão! Dữ liệu đã được nạp đầy đủ vào **Bảng Giám sát**.")


# ══════════════════════════════════════════════════════════
# TAB 3: CÀI ĐẶT CẢNH BÁO
# ══════════════════════════════════════════════════════════
with tab3:
    st.subheader("⚙️ Cài đặt Kênh Cảnh báo & Tích hợp Telegram")

    st.markdown(
        """
        **Hướng dẫn tích hợp thông báo về điện thoại/nhóm Telegram trường:**
        1. Nhắn tin cho [@BotFather](https://t.me/BotFather) trên Telegram $\\rightarrow$ Gửi lệnh `/newbot` để lấy **Token**.
        2. Thêm Bot vào nhóm hoặc chat riêng với bot, truy cập `https://api.telegram.org/bot<TOKEN>/getUpdates` để lấy **Chat ID**.
        3. Điền Token & Chat ID vào biểu mẫu dưới đây để lưu cấu hình.
        """
    )

    with st.form("telegram_config_form"):
        token_input = st.text_input(
            "🤖 Telegram Bot Token",
            type="password",
            placeholder="VD: 7123456789:AAHdqTcvCH1vGWJxfSeofSs4tHF7lvNVjTo",
        )
        chat_id_input = st.text_input(
            "💬 Chat ID hoặc Group ID",
            placeholder="VD: -1001234567890",
        )
        save_btn = st.form_submit_button("💾 Lưu cấu hình Telegram", type="primary")

    if save_btn:
        if token_input and chat_id_input:
            save_config(token_input, chat_id_input)
            notifier.reload_config()
            st.success("✅ Đã lưu cấu hình kết nối Telegram thành công!")
        else:
            st.error("❌ Vui lòng nhập đầy đủ cả Token và Chat ID.")

    st.divider()
    st.subheader("🔔 Kiểm tra kết nối")
    if st.button("📤 Gửi tin nhắn cảnh báo thử nghiệm ngay", use_container_width=True):
        notifier.reload_config()
        with st.spinner("Đang gửi qua Telegram API..."):
            result_tg = notifier.send_test_alert()
        if result_tg["ok"]:
            st.success("✅ Gửi thành công! Hãy kiểm tra thông báo trong ứng dụng Telegram.")
        else:
            st.error(f"❌ Kết quả: {result_tg['error']}")

    st.divider()
    st.subheader("🗑️ Bảo trì & Quản lý dữ liệu quan trắc")
    c_reset1, c_reset2 = st.columns(2)
    with c_reset1:
        if st.button("🗑️ Xóa toàn bộ lịch sử quan trắc & Reset Model", type="secondary", use_container_width=True):
            engine.clear_history()
            st.session_state.last_result = None
            st.session_state.alert_log = []
            st.success("✅ Toàn bộ bộ nhớ đệm và file `iot_telemetry_history.json` đã được dọn sạch.")
    with c_reset2:
        st.markdown(
            """
            - Model: **Logistic Regression Pipeline** (StandardScaler)
            - Ngưỡng Báo động 1: **200 cm** | Ngưỡng Báo động 2: **300 cm**
            - Độ nhạy nhận diện lũ: **100% Recall**
            """
        )
