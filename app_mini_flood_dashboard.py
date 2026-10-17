"""Dashboard cho pipeline mô hình mini.

Chạy: streamlit run app_mini_flood_dashboard.py
"""

from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from mini_flood.config import MiniFloodSettings
from mini_flood.db import MiniFloodDatabase
from mini_flood.models import RISK_LABELS


st.set_page_config(page_title="Mô phỏng dự báo ngập", page_icon="🌧️", layout="wide")
settings = MiniFloodSettings.from_env()
db = MiniFloodDatabase(settings.database_path)

st.title("🌧️ [MÔ PHỎNG THỬ NGHIỆM] Dự báo nguy cơ ngập")
st.caption("Prototype AI + IoT trên mô hình vật lý thu nhỏ — không phải cảnh báo vận hành cho Hội An.")

device_id = st.sidebar.text_input("Mã thiết bị", "mini-flood-station-01")
history_limit = st.sidebar.slider("Số bản ghi hiển thị", 30, 1000, 240, 10)
if st.sidebar.button("Làm mới"):
    st.rerun()

latest = db.latest(device_id)
rows = db.history(device_id, history_limit)
if latest is None:
    st.info("Chưa có dữ liệu. Hãy chạy API và gửi telemetry từ ESP32 hoặc bộ mô phỏng.")
    st.stop()

risk_15 = latest.get("risk_15m")
risk_30 = latest.get("risk_30m")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Mực nước", f"{latest['water_level_cm']:.1f} cm")
c2.metric("Cường độ mưa", f"{latest['rain_rate_mmh']:.1f} mm/h")
c3.metric("Dự báo 15 phút", RISK_LABELS.get(risk_15, "Đang khởi động"))
c4.metric("Dự báo 30 phút", RISK_LABELS.get(risk_30, "Đang khởi động"))
st.caption(f"Lần thí nghiệm: `{latest.get('experiment_id', 'unassigned')}`")

if latest.get("main_factor"):
    st.warning(f"Nguyên nhân chính: {latest['main_factor']}")
if latest.get("quality_status") != "valid":
    st.error(f"Chất lượng dữ liệu: {latest['quality_status']}")

df = pd.DataFrame(rows)
df["timestamp"] = pd.to_datetime(df["timestamp"])
df = df.sort_values("timestamp")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["timestamp"], y=df["water_level_cm"], name="Mực nước (cm)"))
fig.add_trace(go.Scatter(x=df["timestamp"], y=df["rain_rate_mmh"], name="Mưa (mm/h)", yaxis="y2"))
fig.update_layout(
    height=420,
    xaxis_title="Thời gian",
    yaxis=dict(title="Mực nước (cm)"),
    yaxis2=dict(title="Mưa (mm/h)", overlaying="y", side="right"),
    legend=dict(orientation="h"),
)
st.plotly_chart(fig, use_container_width=True)

display_cols = [
    "timestamp",
    "sequence_no",
    "rain_interval_mm",
    "rain_rate_mmh",
    "water_level_cm",
    "quality_status",
    "risk_15m",
    "risk_30m",
    "main_factor",
]
st.subheader("Dữ liệu gần nhất")
st.dataframe(df[[c for c in display_cols if c in df.columns]].sort_values("timestamp", ascending=False), hide_index=True)

with st.expander("Thông tin kỹ thuật"):
    st.code(
        json.dumps(
            {
                "database": str(settings.database_path),
                "warning_level_cm": settings.warning_level_cm,
                "danger_level_cm": settings.danger_level_cm,
                "latest_model_version": latest.get("model_version"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        language="json",
    )
