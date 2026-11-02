from __future__ import annotations

import os
import smtplib
import threading
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Callable

import requests

from .config import MiniFloodSettings
from .db import MiniFloodDatabase
from .models import ALERT_LABELS
from .notification_settings import load_notification_config


Sender = Callable[[str], tuple[bool, str]]


def format_horizon(seconds: int) -> str:
    return f"{seconds // 60} phút" if seconds % 60 == 0 else f"{seconds} giây"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _fmt_vn_time(value: str) -> str:
    try:
        dt = _parse_iso(value)
        vn_tz = timezone(timedelta(hours=7))
        vn_dt = dt.astimezone(vn_tz)
        return vn_dt.strftime("%H:%M:%S %d/%m/%Y (GMT+7)")
    except Exception:
        return value


def send_telegram(message: str, timeout: float | None = None) -> tuple[bool, str]:
    token = os.getenv("MINI_FLOOD_TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("MINI_FLOOD_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False, "Chưa cấu hình MINI_FLOOD_TELEGRAM_TOKEN/CHAT_ID"
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message},
            timeout=timeout if timeout is not None else load_notification_config().timeout_seconds,
        )
        if response.status_code == 200:
            return True, ""
        return False, f"HTTP {response.status_code}: {response.text[:200]}"
    except requests.RequestException as exc:
        return False, str(exc)


def check_telegram_connection(
    token: str | None = None,
    chat_id: str | None = None,
) -> tuple[bool, str]:
    resolved_token = (token or os.getenv("MINI_FLOOD_TELEGRAM_TOKEN", "")).strip()
    resolved_chat_id = (chat_id or os.getenv("MINI_FLOOD_TELEGRAM_CHAT_ID", "")).strip()
    if not resolved_token:
        return False, "Thiếu MINI_FLOOD_TELEGRAM_TOKEN"
    if not resolved_chat_id:
        return False, "Thiếu MINI_FLOOD_TELEGRAM_CHAT_ID"

    try:
        me_resp = requests.get(f"https://api.telegram.org/bot{resolved_token}/getMe", timeout=load_notification_config().timeout_seconds)
        if me_resp.status_code != 200:
            return False, f"Token không hợp lệ (HTTP {me_resp.status_code}): {me_resp.text[:200]}"
        bot_info = me_resp.json().get("result", {})
        bot_name = bot_info.get("username", "UnknownBot")

        msg = (
            f"[GIÁM SÁT MỰC NƯỚC]\n"
            f"✅ Kết nối thành công tới trạm Mini Flood AI qua Bot @{bot_name}."
        )
        send_resp = requests.post(
            f"https://api.telegram.org/bot{resolved_token}/sendMessage",
            json={"chat_id": resolved_chat_id, "text": msg},
            timeout=10,
        )
        if send_resp.status_code == 200:
            return True, f"Kết nối và gửi tin nhắn thành công tới Bot @{bot_name} (Chat ID: {resolved_chat_id})"
        return False, f"Lỗi gửi tin tới Chat ID (HTTP {send_resp.status_code}): {send_resp.text[:200]}"
    except requests.RequestException as exc:
        return False, f"Lỗi mạng khi kết nối Telegram: {exc}"


def send_email(message: str) -> tuple[bool, str]:
    host = os.getenv("MINI_FLOOD_SMTP_HOST", "").strip()
    port = int(os.getenv("MINI_FLOOD_SMTP_PORT", "587"))
    username = os.getenv("MINI_FLOOD_SMTP_USERNAME", "").strip()
    password = os.getenv("MINI_FLOOD_SMTP_PASSWORD", "")
    recipients = [x.strip() for x in os.getenv("MINI_FLOOD_EMAIL_TO", "").split(",") if x.strip()]
    sender = os.getenv("MINI_FLOOD_EMAIL_FROM", username).strip()
    if not host or not sender or not recipients:
        return False, "Chưa cấu hình SMTP host/from/to"

    mail = EmailMessage()
    mail["Subject"] = "[CẢNH BÁO] Nguy cơ ngập"
    mail["From"] = sender
    mail["To"] = ", ".join(recipients)
    mail.set_content(message)
    try:
        smtp_class = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        with smtp_class(host, port, timeout=load_notification_config().timeout_seconds) as smtp:
            if port != 465:
                smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(mail)
        return True, ""
    except (OSError, smtplib.SMTPException) as exc:
        return False, str(exc)


class AlertManager:
    def __init__(self, db: MiniFloodDatabase, settings: MiniFloodSettings):
        self.db = db
        self.settings = settings
        self.model_version = "unavailable"

    def evaluate_sensor_health(
        self,
        telemetry_id: int,
        device_id: str,
        timestamp: str,
        water_valid: bool,
        rain_valid: bool,
        flags: list[str],
    ) -> int | None:
        """Queue one notification per sensor-state transition, separate from flood alerts."""
        key = f"sensor_state:{device_id}"
        previous = self.db.get_state(key, None)
        current = {"water_valid": water_valid, "rain_valid": rain_valid}
        self.db.set_state(key, current)
        liveness_key = f"device_liveness:{device_id}"
        liveness = self.db.get_state(liveness_key, {"online": True})
        if not bool(liveness.get("online", True)):
            self.db.enqueue_alert(
                telemetry_id,
                device_id,
                f"device:{device_id}:recovery:{timestamp}",
                "device_recovery",
                0,
                f"[GIÁM SÁT MỰC NƯỚC]\n🟢 KẾT NỐI THIẾT BỊ ĐÃ PHỤC HỒI\nTrạm: {device_id}\nThời gian: {_fmt_vn_time(timestamp)}",
            )
        self.db.set_state(liveness_key, {"online": True, "last_seen_at": timestamp})
        if previous is None and water_valid and rain_valid:
            return None
        if previous == current:
            return None
        if water_valid and rain_valid:
            event_type = "sensor_recovery"
            message = f"[GIÁM SÁT MỰC NƯỚC]\n🟢 THIẾT BỊ ĐÃ PHỤC HỒI\nTrạm: {device_id}\nThời gian: {_fmt_vn_time(timestamp)}"
            level = 0
        else:
            event_type = "sensor_fault"
            failed = []
            if not water_valid:
                failed.append("cảm biến mực nước")
            if not rain_valid:
                failed.append("cảm biến mưa")
            message = (
                "[GIÁM SÁT MỰC NƯỚC]\n⚠️ LỖI THIẾT BỊ\n"
                f"Trạm: {device_id}\nLỗi: {', '.join(failed)}\n"
                f"Cờ chất lượng: {', '.join(flags) or 'không rõ'}\nThời gian: {_fmt_vn_time(timestamp)}"
            )
            level = 1
        event_key = f"sensor:{device_id}:{event_type}:{timestamp}"
        return self.db.enqueue_alert(
            telemetry_id, device_id, event_key, event_type, level, message
        )

    def check_device_liveness(self, max_age_seconds: int) -> int:
        queued = 0
        now = _now()
        for item in self.db.station_last_seen():
            last_raw = item.get("last_seen_at")
            if not last_raw:
                continue
            last_seen = _parse_iso(str(last_raw)).astimezone(timezone.utc)
            if (now - last_seen).total_seconds() <= max_age_seconds:
                continue
            device_id = str(item["device_id"])
            key = f"device_liveness:{device_id}"
            state = self.db.get_state(key, {"online": True})
            if not bool(state.get("online", True)):
                continue
            stamp = now.isoformat()
            alert_id = self.db.enqueue_alert(
                None,
                device_id,
                f"device:{device_id}:offline:{stamp}",
                "device_offline",
                1,
                f"[GIÁM SÁT MỰC NƯỚC]\nMẤT DỮ LIỆU THIẾT BỊ\nTrạm: {device_id}\nKhông có gói mới trong hơn {max_age_seconds} giây.",
            )
            self.db.set_state(key, {"online": False, "last_seen_at": last_raw})
            queued += int(alert_id is not None)
        return queued

    def build_message(
        self,
        timestamp: str,
        forecasts: dict[int, float | None],
        features: dict[str, float],
        station: dict,
        alert_level: int,
        main_factor: str,
        event_type: str,
        alert_source: str = "model",
    ) -> str:
        icon_map = {0: "🟢", 1: "🟡", 2: "🔴"}
        icon = icon_map.get(alert_level, "⚪")

        if event_type == "recovery":
            heading = "🟢 TRẠNG THÁI ĐÃ HẠ MỨC"
            conclusion = "🟢 Kết luận: Mực nước đã hạ về mức an toàn và duy trì ổn định."
        elif alert_level == 2:
            heading = "🔴 CẢNH BÁO NGUY CƠ NGẬP (NGUY HIỂM)"
            conclusion = "🔴 Kết luận: Nguy cơ ngập tràn rất cao! Cần kích hoạt phương án ứng phó khẩn cấp."
        elif alert_level == 1:
            heading = "🟡 CẢNH BÁO NGUY CƠ NGẬP"
            conclusion = "🟡 Kết luận: Mực nước hoặc dự báo đang ở mức cảnh báo, cần chú ý theo dõi."
        else:
            heading = "🟢 TRẠNG THÁI BÌNH THƯỜNG"
            conclusion = "🟢 Kết luận: Trạm hoạt động ổn định, mực nước ở mức an toàn."

        def fmt(value: float | None) -> str:
            return "Không có kết quả" if value is None else f"{value:.1f} cm"

        return "\n".join(
            [
                "[GIÁM SÁT MỰC NƯỚC]",
                "",
                heading,
                f"Trạng thái: {icon} {ALERT_LABELS[alert_level]}",
                f"Nguồn cảnh báo: {alert_source}",
                f"Model: {self.model_version}",
                *(f"Dự báo {format_horizon(horizon)}: {fmt(value)}" for horizon, value in sorted(forecasts.items())),
                f"Mực nước hiện tại: {fmt(features.get('water_level_cm'))}",
                f"Ngưỡng cảnh báo: {station['warning_level_cm']:.1f} cm",
                f"Mức tràn: {station['overflow_level_cm']:.1f} cm",
                f"Độ dâng trong {self.settings.ai.data.rise_window_seconds} giây: {fmt(features.get('water_delta_window_cm'))}",
                f"Nguyên nhân: {main_factor}",
                conclusion,
                f"Thời gian đo: {_fmt_vn_time(timestamp)}",
            ]
        )

    def evaluate(
        self,
        telemetry_id: int | None,
        device_id: str,
        timestamp: str,
        forecasts: dict[int, float | None],
        features: dict[str, float],
        station: dict,
        main_factor: str,
        alert_source: str = "model",
        sensor_entering: bool = False,
    ) -> tuple[int, int | None]:
        state_key = f"alert_state:{device_id}"
        state = self.db.get_state(
            state_key,
            {
                "alert_level": 0,
                "recovery_started_at": None,
                "recovery_from_level": None,
                "last_danger_alert_at": None,
            },
        )
        previous = int(state.get("alert_level", 0))
        values = [float(features["water_level_cm"])] if alert_source == "sensor_rule" else []
        controlling_forecasts = forecasts if alert_source == "model" else {}
        values.extend(float(value) for value in controlling_forecasts.values() if value is not None)
        if not values:
            raise ValueError("Cannot evaluate model alert without a model prediction")
        controlling_level = max(values)
        warning = float(station["warning_level_cm"])
        overflow = float(station["overflow_level_cm"])
        if controlling_level >= overflow:
            raw_level = 2
        elif controlling_level >= warning:
            raw_level = 1
        else:
            raw_level = 0

        measured_at = _parse_iso(timestamp)
        now = measured_at.astimezone(timezone.utc)
        delivery_now = _now()
        current = previous
        event_type: str | None = None

        if raw_level > previous:
            current = raw_level
            event_type = "escalation"
            state["recovery_started_at"] = None
            state["recovery_from_level"] = None
        elif raw_level < previous:
            boundary = overflow if previous == 2 else warning
            release_level = boundary - float(station["hysteresis_cm"])
            started_raw = state.get("recovery_started_at")
            recovery_from = state.get("recovery_from_level")
            if controlling_level < release_level:
                if started_raw is None or recovery_from != previous:
                    state["recovery_started_at"] = now.isoformat()
                    state["recovery_from_level"] = previous
                else:
                    started = _parse_iso(started_raw)
                    elapsed = (now - started).total_seconds()
                    if elapsed < 0:
                        state["recovery_started_at"] = now.isoformat()
                    elif elapsed >= int(station["recovery_hold_seconds"]):
                        current = previous - 1
                        event_type = "recovery"
                        state["recovery_started_at"] = None
                        state["recovery_from_level"] = None
            else:
                state["recovery_started_at"] = None
                state["recovery_from_level"] = None
        else:
            state["recovery_started_at"] = None
            state["recovery_from_level"] = None

        if current == 2 and event_type is None and alert_source == "sensor_rule" and sensor_entering:
            event_type = "sensor_overflow"
        if current == 2 and event_type is None:
            last_raw = state.get("last_danger_alert_at")
            last = _parse_iso(last_raw) if last_raw else None
            if last is None or delivery_now - last >= timedelta(minutes=self.settings.reminder_minutes):
                event_type = "reminder"

        if event_type in {"escalation", "reminder", "sensor_overflow"} and current == 2:
            state["last_danger_alert_at"] = delivery_now.isoformat()
        state["alert_level"] = current
        state["alert_source"] = alert_source
        self.db.set_state(state_key, state)

        if event_type is None:
            return current, None
        message = self.build_message(
            timestamp, forecasts, features, station, current, main_factor, event_type,
            alert_source=alert_source
        )
        event_key = f"{device_id}:{telemetry_id}:{event_type}:{current}"
        alert_id = self.db.enqueue_alert(
            telemetry_id, device_id, event_key, event_type, current, message
        )
        return current, alert_id

    def enqueue_test(self, device_id: str) -> int | None:
        stamp = _now().isoformat()
        return self.db.enqueue_alert(
            None,
            device_id,
            f"{device_id}:test:{stamp}",
            "test",
            1,
            "[GIÁM SÁT MỰC NƯỚC]\n\nTin nhắn kiểm tra Telegram và email.",
        )


class DeliveryWorker:
    def __init__(
        self,
        db: MiniFloodDatabase,
        telegram_sender: Sender = send_telegram,
        email_sender: Sender = send_email,
        settings: MiniFloodSettings | None = None,
    ):
        self.db = db
        self.senders = {"telegram": telegram_sender, "email": email_sender}
        self.settings = settings or MiniFloodSettings()
        self.db.delivery_config = self.settings.notifications
        self._lock = threading.Lock()

    def process_due(self) -> int:
        if not self._lock.acquire(blocking=False):
            return 0
        try:
            return self._process_due()
        finally:
            self._lock.release()

    def _process_due(self) -> int:
        processed = 0
        for _ in range(self.settings.notifications.batch_size):
            item = self.db.claim_delivery()
            if item is None:
                break
            sender = self.senders.get(item["channel"])
            configured = (bool(os.getenv("MINI_FLOOD_TELEGRAM_TOKEN") and os.getenv("MINI_FLOOD_TELEGRAM_CHAT_ID"))
                          if sender is send_telegram else
                          bool(os.getenv("MINI_FLOOD_SMTP_HOST") and os.getenv("MINI_FLOOD_EMAIL_TO"))
                          if sender is send_email else True)
            if not configured:
                self.db.disable_delivery(int(item["id"]), item["claim_token"])
                processed += 1
                continue
            if sender is None:
                ok, error = False, f"Kênh không hỗ trợ: {item['channel']}"
            else:
                try:
                    ok, error = (sender(item["message"], timeout=self.settings.notifications.timeout_seconds)
                                 if sender is send_telegram else sender(item["message"]))
                except Exception as exc:
                    ok, error = False, f"{type(exc).__name__}: {exc}"
            self.db.update_delivery(int(item["id"]), ok, error, item["claim_token"])
            processed += 1
        return processed


def main() -> int:
    import argparse
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Kiem tra ket noi va gui tin nhan thu nghiem toi Telegram Bot cho Mini Flood AI."
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Telegram Bot Token (neu khong cung cap se doc tu bien MINI_FLOOD_TELEGRAM_TOKEN)",
    )
    parser.add_argument(
        "--chat-id",
        default=None,
        help="Telegram Chat ID (neu khong cung cap se doc tu bien MINI_FLOOD_TELEGRAM_CHAT_ID)",
    )
    args = parser.parse_args()
    ok, message = check_telegram_connection(args.token, args.chat_id)
    if ok:
        print(f"[THÀNH CÔNG] {message}")
        return 0
    print(f"[THẤT BẠI] {message}")
    return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
