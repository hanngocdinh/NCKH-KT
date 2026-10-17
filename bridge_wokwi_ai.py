"""
bridge_wokwi_ai.py — Cầu nối trực tiếp giữa Giả lập Wokwi và Model AI
THPT Trần Quý Cáp, Hội An

Cách hoạt động:
  1. Mở HTTP server tại http://localhost:8000/api/infer
  2. Cung cấp CLI tương tác: bạn có thể paste thẳng dòng JSON xuất ra từ Serial Monitor của Wokwi vào đây
  3. Hoặc nhận request từ web/app và trả về suy luận AI ngay lập tức

Chạy:
  python bridge_wokwi_ai.py
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict

from iot_core_engine import IoTCoreEngine

def run_interactive_serial_bridge():
    print("=" * 65)
    print("🤖 CẦU NỐI WOKWI ARDUINO UNO <---> AI CORE ENGINE")
    print("   Trường THPT Trần Quý Cáp — Hội An")
    print("=" * 65)
    print("\n[HƯỚNG DẪN]")
    print("1. Mở Wokwi: https://wokwi.com/projects/new/arduino-uno")
    print("2. Chạy mô phỏng, Wokwi Serial Monitor sẽ xuất JSON mẫu:")
    print('   {"water_level_cm": 285.0, "rain_daily_mm": 65.0, "delta_water_level_cm": 35.0}')
    print("3. Copy dòng JSON đó dán vào đây (hoặc gõ số mực nước) rồi nhấn ENTER.\n")

    engine = IoTCoreEngine()

    while True:
        try:
            raw_input_str = input("\n📥 [Nhập JSON hoặc Mực nước cm từ Wokwi] (hoặc 'exit'): ").strip()
            if not raw_input_str:
                continue
            if raw_input_str.lower() in ("exit", "quit", "q"):
                print("Đã thoát cầu nối.")
                break

            sensor_dict: Dict[str, Any] = {}
            if raw_input_str.startswith("{") and raw_input_str.endswith("}"):
                try:
                    sensor_dict = json.loads(raw_input_str)
                except Exception as e:
                    print(f"❌ JSON không hợp lệ: {e}")
                    continue
            else:
                try:
                    val = float(raw_input_str)
                    sensor_dict = {
                        "water_level_cm": val,
                        "rain_daily_mm": 45.0,
                        "river_discharge_m3s": 650.0,
                    }
                except ValueError:
                    print("❌ Vui lòng nhập chuỗi JSON hoặc một số cm hợp lệ.")
                    continue

            # Chạy suy luận AI
            result = engine.infer(sensor_dict)
            level = result["risk_level"]
            label = result["risk_label"]
            probs = result["probs"]

            print("-" * 50)
            print(f"🔮 [KẾT QUẢ AI SUY LUẬN 24H]")
            print(f"   • Mức rủi ro : {level} ({label})")
            print(f"   • Xác suất lũ: P(Safe)={probs[0]*100:.1f}%, P(Warn)={probs[1]*100:.1f}%, P(Flood)={probs[2]*100:.1f}%")
            print(f"   • Khuyến nghị: {result['action']}")
            print(f"📡 [GỬI PHẢN HỒI VỀ ARDUINO UNO SERIAL]")
            print(f"   >>> RISK:{level}  (Gõ chuỗi này vào Wokwi Serial để Uno đổi màu đèn & còi hú!)")
            print("-" * 50)

        except KeyboardInterrupt:
            print("\nĐã dừng cầu nối.")
            break

if __name__ == "__main__":
    run_interactive_serial_bridge()
