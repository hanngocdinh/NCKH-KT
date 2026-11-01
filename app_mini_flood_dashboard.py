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
from mini_flood.notifications import format_horizon

from mini_flood.config import MiniFloodSettings
from mini_flood.models import ALERT_LABELS
from mini_flood.features import sensor_validity


APP_TITLE = "Giám sát và cảnh báo mực nước"
st.set_page_config(page_title=APP_TITLE, page_icon="🌊", layout="wide")
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

st.title(f"🌊 {APP_TITLE}")
st.caption("Theo dõi mưa, mực nước và dự báo nguy cơ ngập theo thời gian thực.")

device_id = st.sidebar.text_input("Mã thiết bị", settings.default_device_id)
history_limit = st.sidebar.slider("Số bản ghi hiển thị", 30, 1000, 240, 10)
auto_refresh = st.sidebar.checkbox("Tự động làm mới", value=True)
refresh_interval = st.sidebar.number_input("Chu kỳ làm mới (giây)", min_value=0.1, value=float(settings.notifications.dashboard_refresh_seconds))
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

snapshot, snapshot_error = api_get(f"/stations/{encoded_device_id}/snapshot")
latest = ((snapshot or {}).get("current_inference") or (snapshot or {}).get("last_received"))
latest_error = snapshot_error
last_received = (snapshot or {}).get("last_received") or {}
if last_received and (not last_received.get("is_live") or last_received.get("quality_status") != "valid"):
    st.error(f"Gói vừa nhận không đủ chất lượng: {last_received.get('quality_flags')}")
if latest and latest.get("stale"):
    st.error(f"Kết quả đã cũ: {latest.get('age_seconds', 0):.1f} giây; chờ dữ liệu mới")
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
        "Gửi telemetry vào API từ IoT hoặc công cụ HTTP để bắt đầu."
    )
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()
    st.stop()

inference = latest.get("inference") or {}
forecast_items = {
    int(item["horizon_seconds"] if item.get("horizon_seconds") is not None else item["horizon_minutes"] * 60): item for item in inference.get("forecasts", [])
}


c1, c2 = st.columns(2)
measurement = (snapshot or {}).get("current_measurement")
c1.metric("Mực nước hợp lệ gần nhất", f"{measurement['water_level_cm']:.1f} cm" if measurement else "Chưa có")
if measurement:
    c1.caption(f"Tuổi số đo: {measurement.get('age_seconds', 0):.1f} giây")
c2.metric("Cường độ mưa", f"{latest['rain_rate_mmh']:.1f} mm/h" if latest.get("rain_valid") else "Không có số đo hợp lệ")
forecast_columns = st.columns(len(forecast_items)) if forecast_items else []
for column, horizon in zip(forecast_columns, sorted(forecast_items)):
    item = forecast_items.get(horizon, {})
    point = item.get("level_cm")
    value = "Chưa có dự báo" if point is None else f"{point:.1f} cm"
    column.metric(f"Dự báo {format_horizon(horizon)}", value)
    column.caption(f"{item.get('algorithm') or '-'} · {item.get('status') or ''} · {item.get('error') or ''}")
alert_level = latest.get("alert_level")
st.subheader(f"Trạng thái: {ALERT_LABELS.get(alert_level, 'Chưa đủ cơ sở đánh giá')}")
st.caption(f"Nguồn trạng thái: {latest.get('alert_source') or 'chưa có'}")
if inference.get("status") != "ready":
    st.warning(f"AI chưa có kết quả đầy đủ: {inference.get('status')} · {inference.get('reason') or ''}")
if latest.get("warning_level_cm") is not None:
    st.caption(
        f"Ngưỡng cảnh báo: {latest['warning_level_cm']:.1f} cm · "
        f"Mức tràn: {latest['overflow_level_cm']:.1f} cm"
    )
st.caption(
    f"AI: `{inference.get('status', 'warming_up')}` · "
    f"chế độ `{inference.get('mode', 'none')}` · "
    f"model `{inference.get('model_version', 'chưa có')}`"
)

if latest.get("main_factor"):
    st.warning(f"Điều kiện dữ liệu: {latest['main_factor']}")
if latest.get("quality_status") != "valid":
    message = f"Chất lượng dữ liệu: {latest['quality_status']} · {latest.get('quality_flags', '[]')}"
    (st.warning if latest.get("quality_status") == "degraded" else st.error)(message)

df = pd.DataFrame(rows)
for index, row in df.iterrows():
    for item in (row.get("inference") or {}).get("forecasts", []):
        horizon = int(item["horizon_seconds"] if item.get("horizon_seconds") is not None else item["horizon_minutes"] * 60)
        df.at[index, f"forecast_{horizon}s_cm"] = item.get("level_cm")
df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", utc=True)
df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Ho_Chi_Minh")
df = df.sort_values("timestamp")
fig = go.Figure()
water_rows = df[df.apply(lambda row: sensor_validity(row.to_dict())[0], axis=1)]
rain_rows = df[df.apply(lambda row: sensor_validity(row.to_dict())[1], axis=1)]
fig.add_trace(go.Scatter(x=water_rows["timestamp"], y=water_rows["water_level_cm"], name="Mực nước (cm)"))
fig.add_trace(go.Scatter(x=rain_rows["timestamp"], y=rain_rows["rain_rate_mmh"], name="Mưa (mm/h)", yaxis="y2"))
for horizon in sorted(forecast_items):
    column = f"forecast_{horizon}s_cm"
    if column in df.columns:
        forecast_rows = df.dropna(subset=[column])
        fig.add_trace(
            go.Scatter(
                x=forecast_rows["timestamp"] + pd.to_timedelta(horizon, unit="s"),
                y=forecast_rows[column],
                name=f"Dự báo +{format_horizon(horizon)}",
                line=dict(dash="dot"),
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
    *(f"forecast_{horizon}s_cm" for horizon in sorted(forecast_items)),
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
                "inference": inference,
                "snapshot": snapshot,
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
