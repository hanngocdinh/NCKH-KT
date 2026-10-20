"""Dashboard cho pipeline mô hình mini.

Chạy: streamlit run app_mini_flood_dashboard.py
"""

from __future__ import annotations

import json
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

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
auto_refresh = st.sidebar.checkbox("Tự động làm mới", value=True)
refresh_interval = st.sidebar.selectbox("Chu kỳ làm mới", [5, 10, 30], index=0, format_func=lambda x: f"{x} giây")
if st.sidebar.button("Làm mới ngay"):
    st.rerun()

latest = db.latest(device_id)
rows = db.history(device_id, history_limit)
if latest is None:
    st.info("Chưa có dữ liệu. Hãy chạy API và gửi telemetry từ ESP32 hoặc bộ mô phỏng.")
    st.stop()

risk_15 = latest.get("risk_15m")
risk_30 = latest.get("risk_30m")


def confidence(raw: str | None) -> str:
    if not raw:
        return "chưa có"
    try:
        return f"{max(json.loads(raw)) * 100:.1f}%"
    except (TypeError, ValueError, json.JSONDecodeError):
        return "không hợp lệ"


init_water = f"{latest['water_level_cm']:.1f} cm"
init_rain = f"{latest['rain_rate_mmh']:.1f} mm/h"
init_seq = f"#{latest.get('sequence_no', '-')}"

html_stream_widget = """
<div style="background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 10px 16px; margin-bottom: 12px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #f8fafc;">
  <div style="display: flex; justify-content: space-between; align-items: center;">
    <div style="display: flex; align-items: center;">
      <span id="dot" style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #10b981; margin-right: 8px;"></span>
      <span style="font-weight: 600; font-size: 14px; color: #38bdf8;">Lắng nghe dữ liệu thời gian thực (Live SSE Stream):</span>
      <span id="status" style="margin-left: 8px; font-size: 13px; color: #94a3b8;">Đang kết nối...</span>
    </div>
    <div id="recv-time" style="font-size: 12px; color: #94a3b8;">Chờ bản ghi mới...</div>
  </div>
  <div style="display: flex; gap: 24px; margin-top: 8px; font-size: 13px;">
    <div>🌊 Mực nước tức thời: <strong id="val-water" style="color: #67e8f9;">__INIT_WATER__</strong></div>
    <div>🌧️ Cường độ mưa tức thời: <strong id="val-rain" style="color: #67e8f9;">__INIT_RAIN__</strong></div>
    <div>⏱️ Gói đo gần nhất: <strong id="val-seq" style="color: #cbd5e1;">__INIT_SEQ__</strong></div>
  </div>
</div>
<script>
  const source = new EventSource("http://localhost:8000/api/v1/stream/sse");
  const dot = document.getElementById("dot");
  const statusEl = document.getElementById("status");
  const timeEl = document.getElementById("recv-time");
  const waterEl = document.getElementById("val-water");
  const rainEl = document.getElementById("val-rain");
  const seqEl = document.getElementById("val-seq");

  source.onopen = function() {
    statusEl.innerText = "Đã kết nối trực tiếp (Live)";
    statusEl.style.color = "#34d399";
  };
  source.addEventListener("telemetry", function(e) {
    try {
      const item = JSON.parse(e.data);
      waterEl.innerText = Number(item.water_level_cm).toFixed(1) + " cm";
      rainEl.innerText = Number(item.rain_rate_mmh).toFixed(1) + " mm/h";
      seqEl.innerText = "#" + item.sequence_no;
      timeEl.innerText = "Nhận lúc: " + new Date().toLocaleTimeString();
      dot.style.background = "#38bdf8";
      setTimeout(function() { dot.style.background = "#10b981"; }, 300);
    } catch(err) {}
  });
  source.onerror = function() {
    statusEl.innerText = "Chờ máy chủ / Đang kết nối lại...";
    statusEl.style.color = "#f87171";
    dot.style.background = "#ef4444";
  };
</script>
""".replace("__INIT_WATER__", init_water).replace("__INIT_RAIN__", init_rain).replace("__INIT_SEQ__", init_seq)

components.html(html_stream_widget, height=88)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Mực nước", f"{latest['water_level_cm']:.1f} cm")
c2.metric("Cường độ mưa", f"{latest['rain_rate_mmh']:.1f} mm/h")
c3.metric("Dự báo 15 phút", RISK_LABELS.get(risk_15, "Đang khởi động"))
c4.metric("Dự báo 30 phút", RISK_LABELS.get(risk_30, "Đang khởi động"))
c3.caption(f"Confidence: {confidence(latest.get('probs_15m'))}")
c4.caption(f"Confidence: {confidence(latest.get('probs_30m'))}")
st.caption(f"Lần thí nghiệm: `{latest.get('experiment_id', 'unassigned')}`")

if latest.get("main_factor"):
    st.warning(f"Nguyên nhân chính: {latest['main_factor']}")
if latest.get("quality_status") != "valid":
    st.error(f"Chất lượng dữ liệu: {latest['quality_status']}")

df = pd.DataFrame(rows)
df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", utc=True)
df = df[df["timestamp"].dt.year >= 2020]
df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Bangkok")
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

if auto_refresh:
    st.sidebar.caption(f"⏱️ Tự làm mới sau {refresh_interval}s...")
    time.sleep(refresh_interval)
    st.rerun()
