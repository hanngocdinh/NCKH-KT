"""Dashboard cho pipeline mô hình mini.

Chạy: streamlit run app_mini_flood_dashboard.py
"""

from __future__ import annotations

import json
import os
import time
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import streamlit.components.v1 as components

from mini_flood.config import MiniFloodSettings
from mini_flood.models import ALERT_LABELS


st.set_page_config(page_title="Mô phỏng dự báo ngập", page_icon="🌧️", layout="wide")
settings = MiniFloodSettings.from_env()
api_base = os.getenv("MINI_FLOOD_API_BASE", "http://localhost:8000/api/v2").rstrip("/")
api_headers = {"X-Device-Key": settings.device_api_key}


def api_get(path: str) -> tuple[dict | None, str | None]:
    try:
        response = requests.get(f"{api_base}{path}", headers=api_headers, timeout=5)
        if response.status_code == 404:
            return None, None
        response.raise_for_status()
        return response.json(), None
    except requests.RequestException as exc:
        return None, str(exc)

st.title("🌧️ [MÔ PHỎNG THỬ NGHIỆM] Dự báo nguy cơ ngập")
st.caption("Prototype AI + IoT trên mô hình vật lý thu nhỏ — không phải cảnh báo vận hành cho Hội An.")

device_id = st.sidebar.text_input("Mã thiết bị", "mini-flood-station-01")
history_limit = st.sidebar.slider("Số bản ghi hiển thị", 30, 1000, 240, 10)
auto_refresh = st.sidebar.checkbox("Tự động làm mới", value=True)
refresh_interval = st.sidebar.selectbox("Chu kỳ làm mới", [5, 10, 30], index=0, format_func=lambda x: f"{x} giây")
if st.sidebar.button("Làm mới ngay"):
    st.rerun()

encoded_device_id = quote(device_id, safe="")
station, station_error = api_get(f"/stations/{encoded_device_id}/config")
with st.sidebar.expander("Cấu hình ngưỡng động", expanded=False):
    if station_error:
        st.error(f"Không đọc được cấu hình từ API: {station_error}")
    if station is None:
        st.warning("Thiết bị chưa có cấu hình. Nhập thông số để kích hoạt cảnh báo.")
        station = {
            "overflow_level_cm": 40.0,
            "warning_margin_cm": 10.0,
            "hysteresis_cm": 2.0,
            "recovery_hold_seconds": 120,
        }
    with st.form("station-config"):
        overflow = st.number_input("Mức tràn (cm)", min_value=0.1, value=float(station["overflow_level_cm"]))
        margin = st.number_input("Vùng đệm cảnh báo (cm)", min_value=0.1, value=float(station["warning_margin_cm"]))
        hysteresis = st.number_input("Hysteresis (cm)", min_value=0.0, value=float(station["hysteresis_cm"]))
        hold = st.number_input("Thời gian ổn định khi hạ mức (giây)", min_value=0, value=int(station["recovery_hold_seconds"]), step=10)
        confirmed = st.checkbox("Xác nhận cập nhật cấu hình trạm")
        submitted = st.form_submit_button("Lưu cấu hình")
        if submitted:
            if not confirmed:
                st.error("Hãy xác nhận trước khi lưu.")
            else:
                try:
                    response = requests.put(
                        f"{api_base}/stations/{device_id}/config",
                        headers=api_headers,
                        json={
                            "overflow_level_cm": overflow,
                            "warning_margin_cm": margin,
                            "hysteresis_cm": hysteresis,
                            "recovery_hold_seconds": hold,
                        },
                        timeout=5,
                    )
                    response.raise_for_status()
                    st.success("Đã cập nhật cấu hình trạm.")
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(f"Không thể cập nhật qua API: {exc}")

latest, latest_error = api_get(f"/stations/{encoded_device_id}/latest")
history_payload, history_error = api_get(
    f"/stations/{encoded_device_id}/history?limit={history_limit}"
)
if latest_error or history_error:
    st.error(
        "Không thể đọc dữ liệu từ backend. "
        f"Latest: {latest_error or 'OK'}; History: {history_error or 'OK'}"
    )
    st.stop()
rows = (history_payload or {}).get("items", [])
if latest is None:
    st.info(
        "Backend đang hoạt động nhưng chưa có telemetry cho thiết bị này. "
        "Hãy kiểm tra Serial Monitor của ESP32/Wokwi."
    )
    st.stop()

forecast_15 = latest.get("forecast_15m_cm")
forecast_30 = latest.get("forecast_30m_cm")


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
  const source = new EventSource("__SSE_URL__");
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
"""
sse_url = f"{api_base}/stream/sse?device_id={encoded_device_id}"
html_stream_widget = (
    html_stream_widget
    .replace("__INIT_WATER__", init_water)
    .replace("__INIT_RAIN__", init_rain)
    .replace("__INIT_SEQ__", init_seq)
    .replace("__SSE_URL__", sse_url)
)

components.html(html_stream_widget, height=88)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Mực nước", f"{latest['water_level_cm']:.1f} cm")
c2.metric("Cường độ mưa", f"{latest['rain_rate_mmh']:.1f} mm/h")
c3.metric("Dự báo 15 phút", "Đang khởi động" if forecast_15 is None else f"{forecast_15:.1f} cm")
c4.metric("Dự báo 30 phút", "Đang khởi động" if forecast_30 is None else f"{forecast_30:.1f} cm")
alert_level = latest.get("alert_level")
st.subheader(f"Trạng thái: {ALERT_LABELS.get(alert_level, 'Đang khởi động')}")
if latest.get("warning_level_cm") is not None:
    st.caption(
        f"Ngưỡng cảnh báo: {latest['warning_level_cm']:.1f} cm · "
        f"Mức tràn: {latest['overflow_level_cm']:.1f} cm"
    )
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
for horizon, column, color in ((15, "forecast_15m_cm", "#f59e0b"), (30, "forecast_30m_cm", "#ef4444")):
    if column in df.columns:
        forecast_rows = df.dropna(subset=[column])
        fig.add_trace(
            go.Scatter(
                x=forecast_rows["timestamp"] + pd.to_timedelta(horizon, unit="m"),
                y=forecast_rows[column],
                name=f"Dự báo +{horizon} phút",
                line=dict(dash="dot", color=color),
            )
        )
if latest.get("warning_level_cm") is not None:
    fig.add_hline(y=latest["warning_level_cm"], line_dash="dash", line_color="#f59e0b", annotation_text="Cảnh báo")
    fig.add_hline(y=latest["overflow_level_cm"], line_dash="dash", line_color="#ef4444", annotation_text="Mức tràn")
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
    "forecast_15m_cm",
    "forecast_30m_cm",
    "alert_level",
    "main_factor",
]
st.subheader("Dữ liệu gần nhất")
st.dataframe(df[[c for c in display_cols if c in df.columns]].sort_values("timestamp", ascending=False), hide_index=True)

with st.expander("Thông tin kỹ thuật"):
    st.code(
        json.dumps(
            {
                "api": api_base,
                "warning_level_cm": latest.get("warning_level_cm"),
                "overflow_level_cm": latest.get("overflow_level_cm"),
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
