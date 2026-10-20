"""Công cụ giả lập thiết bị IoT gửi telemetry kiểm thử toàn bộ hệ thống Mini Flood.

Chạy:
    python simulate_iot_stream.py --scenario flow --speedup 0.5
    python simulate_iot_stream.py --scenario normal --count 10
    python simulate_iot_stream.py --scenario danger --count 5
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

API_URL = os.getenv("MINI_FLOOD_API_URL", "http://localhost:8000/api/v1/telemetry")
DEVICE_KEY = os.getenv("MINI_FLOOD_DEVICE_KEY", "change-me")
DEVICE_ID = "mini-flood-station-01"


def send_telemetry(seq: int, ts: datetime, rain_mm: float, rain_rate: float, water_cm: float) -> dict:
    payload = {
        "schema_version": 1,
        "device_id": DEVICE_ID,
        "sequence_no": seq,
        "timestamp": ts.isoformat(),
        "rain_interval_mm": round(rain_mm, 3),
        "rain_rate_mmh": round(rain_rate, 2),
        "water_level_cm": round(water_cm, 2),
        "quality_flags": [],
    }
    headers = {
        "Content-Type": "application/json",
        "X-Device-Key": DEVICE_KEY,
    }
    resp = requests.post(API_URL, json=payload, headers=headers, timeout=5)
    resp.raise_for_status()
    return resp.json()


def run_scenario(scenario: str, count: int, interval_seconds: float):
    print(f"\n=======================================================")
    print(f"🚀 BẮT ĐẦU MÔ PHỎNG IOT: Kịch bản '{scenario}'")
    print(f"📍 Target API: {API_URL}")
    print(f"📡 Thiết bị giả lập: {DEVICE_ID} (2 cảm biến siêu âm)")
    print(f"=======================================================\n")

    base_time = datetime.now(timezone.utc) - timedelta(minutes=count)
    seq = int(time.time()) % 100000

    if scenario == "normal":
        records = [
            (5.0 + (i % 3) * 2.0, 8.0 + (i % 4) * 1.0) for i in range(count)
        ]
    elif scenario == "warning":
        records = [
            (25.0 + (i % 5) * 3.0, 16.0 + i * 0.5) for i in range(count)
        ]
    elif scenario == "danger":
        records = [
            (60.0 + (i % 4) * 8.0, 24.0 + i * 1.5) for i in range(count)
        ]
    elif scenario == "flow":
        # Chu kỳ hoàn chỉnh: Khởi động an toàn (15 bản ghi) -> Mưa dồn dập (5 bản ghi) -> Nguy hiểm (5 bản ghi) -> Nước rút an toàn (5 bản ghi)
        records = []
        # Phase 1: 15 bản ghi bình thường (vượt qua giai đoạn warming up 15 phút)
        for i in range(15):
            records.append((8.0, 6.0 + i * 0.2))
        # Phase 2: Mưa to dồn dập, nước dâng vào mức cảnh báo (Mức 1)
        for i in range(5):
            records.append((35.0 + i * 5.0, 15.0 + i * 1.8))
        # Phase 3: Nguy hiểm cao (Mực nước >= 25 cm, Mức 2)
        for i in range(5):
            records.append((75.0 + i * 3.0, 26.0 + i * 1.2))
        # Phase 4: Mưa tạnh, nước rút an toàn
        for i in range(5):
            records.append((2.0, max(5.0, 24.0 - i * 4.0)))
    else:
        print(f"❌ Kịch bản '{scenario}' không hợp lệ. Chọn: normal, warning, danger, flow")
        sys.exit(1)

    total = len(records)
    for idx, (rain_rate, water_cm) in enumerate(records, start=1):
        seq += 1
        curr_time = base_time + timedelta(minutes=idx)
        rain_mm = rain_rate * (1.0 / 60.0)

        try:
            ack = send_telemetry(seq, curr_time, rain_mm, rain_rate, water_cm)
            print(
                f"[{idx:02d}/{total:02d}] Seq={seq:05d} | "
                f"🌧️ Mưa: {rain_rate:4.1f} mm/h | 🌊 Mực nước: {water_cm:4.1f} cm | "
                f"Status: {ack.get('quality_status')} | Accepted: {ack.get('accepted')}"
            )
        except Exception as e:
            print(f"[{idx:02d}/{total:02d}] ❌ Gửi thất bại: {e}")

        if interval_seconds > 0 and idx < total:
            time.sleep(interval_seconds)

    print(f"\n✅ Đã hoàn tất truyền {total} bản ghi telemetry!")
    print(f"👉 Mở Dashboard tại http://localhost:8501 để xem biểu đồ và kết quả AI dự báo.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IoT Telemetry Stream Simulator")
    parser.add_argument(
        "--scenario",
        default="flow",
        choices=["flow", "normal", "warning", "danger"],
        help="Kịch bản giả lập (mặc định: flow)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="Số lượng bản ghi (cho kịch bản normal/warning/danger)",
    )
    parser.add_argument(
        "--speedup",
        type=float,
        default=0.2,
        help="Khoảng dừng giữa các lần gửi tính bằng giây (0 để gửi siêu tốc)",
    )
    args = parser.parse_args()
    run_scenario(args.scenario, args.count, args.speedup)
