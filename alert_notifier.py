"""
alert_notifier.py — Bộ điều phối cảnh báo đa kênh
THPT Trần Quý Cáp, Hội An

Kênh hỗ trợ:
- Telegram Bot (qua requests.post — không cần thư viện bên ngoài)
- Web audio (buzzer trong trình duyệt — tạo script JS để Streamlit phát âm)

Cooldown: 15 phút / mức rủi ro để tránh spam.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

ALERT_CONFIG_FILE = Path(__file__).parent / "config_alerts.json"
COOLDOWN_MINUTES = 15

RISK_EMOJIS = {0: "✅", 1: "⚠️", 2: "🚨"}
RISK_LABELS = {0: "An toàn", 1: "Cảnh báo", 2: "Nguy hiểm cao"}


def _load_config() -> dict:
    if ALERT_CONFIG_FILE.exists():
        try:
            with open(ALERT_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"telegram_token": "", "telegram_chat_id": "", "last_alerts": {}}


def save_config(token: str, chat_id: str):
    """Lưu cấu hình Telegram vào file."""
    cfg = _load_config()
    cfg["telegram_token"] = token.strip()
    cfg["telegram_chat_id"] = chat_id.strip()
    with open(ALERT_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


class AlertNotifier:
    """Điều phối cảnh báo với kiểm soát cooldown."""

    def __init__(self):
        self._last_alert_times: dict[int, Optional[datetime]] = {0: None, 1: None, 2: None}
        cfg = _load_config()
        self._token: str = cfg.get("telegram_token", "")
        self._chat_id: str = cfg.get("telegram_chat_id", "")

    def reload_config(self):
        cfg = _load_config()
        self._token = cfg.get("telegram_token", "")
        self._chat_id = cfg.get("telegram_chat_id", "")

    # ------------------------------------------------------------------
    # Cooldown check
    # ------------------------------------------------------------------
    def _is_in_cooldown(self, risk_level: int) -> bool:
        last = self._last_alert_times.get(risk_level)
        if last is None:
            return False
        return datetime.now() - last < timedelta(minutes=COOLDOWN_MINUTES)

    def _record_alert(self, risk_level: int):
        self._last_alert_times[risk_level] = datetime.now()

    # ------------------------------------------------------------------
    # Message builder
    # ------------------------------------------------------------------
    @staticmethod
    def _build_message(result: dict) -> str:
        emoji = RISK_EMOJIS[result["risk_level"]]
        label = RISK_LABELS[result["risk_level"]]
        f = result.get("features", {})
        probs = result.get("probs", [0, 0, 0])
        ts = result.get("timestamp", "")[:19].replace("T", " ")

        lines = [
            f"{emoji} *CẢNH BÁO LŨ LỤT AI* {emoji}",
            f"🏫 THPT Trần Quý Cáp — Hội An",
            f"🕐 Thời gian: `{ts}`",
            "",
            f"📊 *Mức cảnh báo: {label.upper()}*",
            f"🔮 Dự báo 24h tới:",
            f"   • An toàn: {probs[0]*100:.1f}%",
            f"   • Cảnh báo: {probs[1]*100:.1f}%",
            f"   • Nguy hiểm: {probs[2]*100:.1f}%",
            "",
            "🌊 *Số liệu cảm biến:*",
            f"   • Mực nước: {f.get('water_level_cm', 0):.0f} cm",
            f"   • Mưa ngày: {f.get('rain_daily_mm', 0):.1f} mm",
            f"   • Lưu lượng sông: {f.get('river_discharge_m3s', 0):.0f} m³/s",
            f"   • Δ mực nước: {f.get('delta_water_level_cm', 0):+.1f} cm",
            "",
            f"📢 *Hành động:* {result.get('action', '')}",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Telegram
    # ------------------------------------------------------------------
    def send_telegram(self, result: dict, force: bool = False) -> dict:
        """
        Gửi cảnh báo qua Telegram.
        Returns: {"ok": bool, "skipped": bool, "error": str}
        """
        risk_level = result.get("risk_level", 0)

        if not force and self._is_in_cooldown(risk_level):
            return {"ok": False, "skipped": True, "error": "Đang trong cooldown 15 phút"}

        if not self._token or not self._chat_id:
            return {"ok": False, "skipped": False, "error": "Chưa cấu hình Telegram Token / Chat ID"}

        message = self._build_message(result)
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        try:
            resp = requests.post(
                url,
                json={"chat_id": self._chat_id, "text": message, "parse_mode": "Markdown"},
                timeout=10,
            )
            if resp.status_code == 200:
                self._record_alert(risk_level)
                return {"ok": True, "skipped": False, "error": ""}
            else:
                return {
                    "ok": False,
                    "skipped": False,
                    "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                }
        except requests.RequestException as e:
            return {"ok": False, "skipped": False, "error": str(e)}

    def send_test_alert(self) -> dict:
        """Gửi cảnh báo thử nghiệm không bị cooldown."""
        test_result = {
            "risk_level": 1,
            "features": {
                "water_level_cm": 180,
                "rain_daily_mm": 45.0,
                "river_discharge_m3s": 800,
                "delta_water_level_cm": 10,
            },
            "probs": [0.1, 0.7, 0.2],
            "action": "Đây là tin nhắn thử nghiệm — hệ thống hoạt động bình thường.",
            "timestamp": datetime.now().isoformat(),
        }
        return self.send_telegram(test_result, force=True)

    # ------------------------------------------------------------------
    # Auto-dispatch (gọi sau mỗi lần infer nếu risk >= 1)
    # ------------------------------------------------------------------
    def dispatch(self, result: dict) -> dict:
        """Tự động gửi Telegram nếu risk_level >= 1 và không trong cooldown."""
        if result.get("risk_level", 0) >= 1:
            return self.send_telegram(result)
        return {"ok": False, "skipped": True, "error": "Mức an toàn, không cần cảnh báo"}
