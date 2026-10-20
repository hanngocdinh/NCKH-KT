"""Công cụ dòng lệnh lắng nghe dữ liệu mực nước và cường độ mưa thời gian thực.

Hỗ trợ 2 chế độ:
1. SSE (Server-Sent Events) - mặc định:
   python listen_realtime_stream.py --mode sse
2. WebSocket:
   python listen_realtime_stream.py --mode ws
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

import requests


def listen_sse(url: str, device_id: str | None = None) -> None:
    target_url = f"{url}?device_id={device_id}" if device_id else url
    print(f"\n=======================================================")
    print(f"🛰️  ĐANG LẮNG NGHE LUỒNG DỮ LIỆU SSE THỜI GIAN THỰC")
    print(f"📍 Target: {target_url}")
    print(f"👉 Nhấn Ctrl+C để dừng lắng nghe.")
    print(f"=======================================================\n")

    try:
        with requests.get(target_url, stream=True, timeout=None) as response:
            if response.status_code != 200:
                print(f"❌ Kết nối thất bại: HTTP {response.status_code}")
                return

            print("🟢 Đã kết nối thành công! Đang chờ bản ghi đo mới...\n")
            current_event = None

            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8").strip()
                if line.startswith("event:"):
                    current_event = line[6:].strip()
                elif line.startswith("data:"):
                    data_str = line[5:].strip()
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    if current_event == "connected":
                        print(f"🤝 [SERVER] Xác nhận kết nối: {data.get('status')}")
                    elif current_event == "telemetry" or "water_level_cm" in data:
                        seq = data.get("sequence_no", "-")
                        dev = data.get("device_id", "station")
                        water = float(data.get("water_level_cm", 0.0))
                        rain = float(data.get("rain_rate_mmh", 0.0))
                        status = data.get("quality_status", "valid")

                        pred_15 = "Chưa có"
                        forecast_15 = data.get("forecast_15m_cm")
                        if forecast_15 is not None:
                            pred_15 = f"{float(forecast_15):.1f} cm"

                        now_str = datetime.now().strftime("%H:%M:%S")
                        print(
                            f"[{now_str}] 📡 {dev} | Seq={seq:04} | "
                            f"🌊 Nước: {water:4.1f} cm | "
                            f"🌧️ Mưa: {rain:4.1f} mm/h | "
                            f"🎯 Dự báo 15m: {pred_15} | "
                            f"Trạng thái: {status}"
                        )
    except KeyboardInterrupt:
        print("\n👋 Đã ngắt kết nối lắng nghe.")
    except Exception as exc:
        print(f"\n❌ Lỗi kết nối stream: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Lắng nghe dữ liệu IoT thời gian thực")
    parser.add_argument("--url", default="http://localhost:8000/api/v2/stream/sse", help="URL stream SSE")
    parser.add_argument("--device-id", default=None, help="Lọc theo mã thiết bị")
    args = parser.parse_args()
    listen_sse(args.url, args.device_id)


if __name__ == "__main__":
    main()
