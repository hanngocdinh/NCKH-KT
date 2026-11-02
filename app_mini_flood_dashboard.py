"""Dashboard cho pipeline mô hình mini.

Chạy: streamlit run app_mini_flood_dashboard.py
"""

from __future__ import annotations

import json
import os
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from mini_flood.notifications import format_horizon

from mini_flood.config import MiniFloodSettings
from mini_flood.dashboard_view import select_model_forecasts, station_device_ids
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

stations_payload, stations_error = api_get("/stations")
if stations_error:
    st.error(f"Không đọc được danh sách thiết bị: {stations_error}")
device_ids = station_device_ids(stations_payload, settings.default_device_id)
selected_device = st.session_state.get("selected_device_id")
if isinstance(selected_device, str) and selected_device.strip():
    selected_device = selected_device.strip()
    if selected_device not in device_ids:
        device_ids.insert(0, selected_device)
else:
    st.session_state["selected_device_id"] = (
        settings.default_device_id if settings.default_device_id in device_ids else device_ids[0]
    )
device_column, refresh_devices_column = st.columns([4, 1], vertical_alignment="bottom")
with device_column:
    device_id = st.selectbox(
        "Chọn hoặc nhập mã thiết bị",
        device_ids,
        key="selected_device_id",
        accept_new_options=True,
        help="Chọn trong danh sách hoặc nhập đầy đủ mã thiết bị rồi nhấn Enter.",
    )
with refresh_devices_column:
    if st.button("Làm mới danh sách", use_container_width=True):
        st.rerun()

history_limit = st.sidebar.slider("Số bản ghi hiển thị", 30, 1000, 240, 10)
auto_refresh = st.sidebar.checkbox("Tự động làm mới", value=True)
refresh_interval = st.sidebar.number_input("Chu kỳ làm mới giao diện (giây)", min_value=0.1, value=float(settings.notifications.dashboard_refresh_seconds))
if st.sidebar.button("Làm mới ngay"):
    st.rerun()
if auto_refresh:
    st.sidebar.caption(f"Dữ liệu tự cập nhật mỗi {refresh_interval:g} giây")

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
                        f"{api_base}/stations/{encoded_device_id}/config",
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

@st.fragment(run_every=refresh_interval if auto_refresh else None)
def render_live_data(selected_device_id: str, selected_history_limit: int) -> None:
    selected_encoded_device_id = quote(selected_device_id, safe="")
    snapshot, snapshot_error = api_get(f"/stations/{selected_encoded_device_id}/snapshot")
    latest = ((snapshot or {}).get("current_inference") or (snapshot or {}).get("last_received"))
    last_received = (snapshot or {}).get("last_received") or {}
    if last_received and (not last_received.get("is_live") or last_received.get("quality_status") != "valid"):
        st.warning("Dữ liệu mới nhất chưa đạt chất lượng và không được dùng để thay số đo hiện tại.")
    if latest and latest.get("stale"):
        st.warning("Dữ liệu hiện tại đã cũ; đang chờ mẫu mới từ thiết bị.")
    history_payload, history_error = api_get(
        f"/stations/{selected_encoded_device_id}/history?limit={selected_history_limit}"
    )
    if snapshot_error or history_error:
        st.error("Không thể đọc dữ liệu từ backend.")
        return
    rows = (history_payload or {}).get("items", [])
    if latest is None:
        st.info("Chưa có dữ liệu cho thiết bị này.")
        return

    inference = latest.get("inference") or {}
    forecast_items, forecast_issues = select_model_forecasts(inference)

    st.subheader("Dữ liệu cảm biến")
    c1, c2 = st.columns(2)
    measurement = (snapshot or {}).get("current_measurement")
    c1.metric("Mực nước hợp lệ gần nhất", f"{measurement['water_level_cm']:.1f} cm" if measurement else "Chưa có")
    c2.metric("Cường độ mưa", f"{latest['rain_rate_mmh']:.1f} mm/h" if latest.get("rain_valid") else "Không có số đo hợp lệ")

    st.subheader("Dự báo AI")
    forecast_columns = st.columns(len(forecast_items)) if forecast_items else []
    for column, horizon in zip(forecast_columns, sorted(forecast_items)):
        item = forecast_items.get(horizon, {})
        column.metric(f"Dự báo sau {format_horizon(horizon)}", f"{item['level_cm']:.1f} cm")
        if item.get("target_timestamp"):
            try:
                pd.to_datetime(item["target_timestamp"], utc=True)
            except (TypeError, ValueError):
                forecast_issues.append(f"forecast_{horizon}s_invalid_target_timestamp")
    if not forecast_items:
        st.info("Đang chờ đủ dữ liệu để tạo dự báo.")

    alert_level = latest.get("alert_level")
    st.subheader(f"Trạng thái: {ALERT_LABELS.get(alert_level, 'Chưa đủ dữ liệu')}")
    if inference.get("status") != "ready":
        st.caption("AI đang thu thập thêm dữ liệu hợp lệ.")
    if latest.get("quality_status") == "invalid":
        st.error("Mẫu dữ liệu hiện tại không hợp lệ nên không được dùng để dự báo.")
    elif latest.get("quality_status") == "stale":
        st.warning("Mẫu dữ liệu hiện tại đã cũ nên không được dùng để dự báo.")

    df = pd.DataFrame(rows)
    if df.empty or "timestamp" not in df.columns:
        st.info("Chưa có lịch sử dữ liệu để vẽ biểu đồ.")
        return
    for index, row in df.iterrows():
        history_forecasts, _ = select_model_forecasts(row.get("inference"), require_ready=False)
        for horizon, item in history_forecasts.items():
            if horizon in forecast_items:
                df.at[index, f"forecast_{horizon}s_cm"] = item["level_cm"]
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
                    name=f"AI dự báo +{format_horizon(horizon)}",
                    line=dict(dash="dot"),
                )
            )
    if latest.get("warning_level_cm") is not None:
        fig.add_hline(y=latest["warning_level_cm"], line_dash="dash", line_color="#f59e0b", annotation_text="Ngưỡng cảnh báo (cấu hình)")
        fig.add_hline(y=latest["overflow_level_cm"], line_dash="dash", line_color="#ef4444", annotation_text="Mức tràn (cấu hình)")
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
        "water_level_cm",
        "rain_rate_mmh",
        *(f"forecast_{horizon}s_cm" for horizon in sorted(forecast_items)),
        "alert_label",
    ]
    st.subheader("Dữ liệu gần nhất")
    display_df = df[[c for c in display_cols if c in df.columns]].sort_values("timestamp", ascending=False).copy()
    column_labels = {
        "timestamp": "Thời gian",
        "water_level_cm": "Mực nước (cm)",
        "rain_rate_mmh": "Mưa (mm/h)",
        "alert_label": "Trạng thái",
    }
    for horizon in sorted(forecast_items):
        column_labels[f"forecast_{horizon}s_cm"] = f"Dự báo +{format_horizon(horizon)} (cm)"
    st.dataframe(display_df.rename(columns=column_labels), hide_index=True)

    with st.expander("Chi tiết kỹ thuật", expanded=False):
        st.markdown(
            "**Chất lượng dữ liệu (`quality_status`)**  \n"
            "- `valid`: mẫu mới, đúng thời gian và cảm biến hợp lệ.  \n"
            "- `stale`: mẫu đến quá muộn; chỉ lưu lịch sử.  \n"
            "- `invalid`: lỗi thời gian, sai thứ tự hoặc cảm biến không hợp lệ."
        )
        st.code(
            json.dumps(
                {
                    "api": api_base,
                    "warning_level_cm": latest.get("warning_level_cm"),
                    "overflow_level_cm": latest.get("overflow_level_cm"),
                    "forecast_validation_issues": forecast_issues,
                    "inference": inference,
                    "snapshot": snapshot,
                },
                ensure_ascii=False,
                indent=2,
            ),
            language="json",
        )


render_live_data(device_id, history_limit)
