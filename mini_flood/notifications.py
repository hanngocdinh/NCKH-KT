from __future__ import annotations

import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Callable

import requests

from .config import MiniFloodSettings
from .db import MiniFloodDatabase
from .models import ALERT_LABELS


Sender = Callable[[str], tuple[bool, str]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def send_telegram(message: str) -> tuple[bool, str]:
    token = os.getenv("MINI_FLOOD_TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("MINI_FLOOD_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False, "Chưa cấu hình MINI_FLOOD_TELEGRAM_TOKEN/CHAT_ID"
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message},
            timeout=10,
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
        me_resp = requests.get(f"https://api.telegram.org/bot{resolved_token}/getMe", timeout=10)
        if me_resp.status_code != 200:
            return False, f"Token không hợp lệ (HTTP {me_resp.status_code}): {me_resp.text[:200]}"
        bot_info = me_resp.json().get("result", {})
        bot_name = bot_info.get("username", "UnknownBot")

        msg = (
            f"[MÔ PHỎNG THỬ NGHIỆM]\n"
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
    mail["Subject"] = "[MÔ PHỎNG] Cảnh báo nguy cơ ngập"
    mail["From"] = sender
    mail["To"] = ", ".join(recipients)
    mail.set_content(message)
    try:
        smtp_class = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        with smtp_class(host, port, timeout=10) as smtp:
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

    @staticmethod
    def build_message(
        timestamp: str,
        forecasts: dict[int, float | None],
        features: dict[str, float],
        station: dict,
        alert_level: int,
        main_factor: str,
        event_type: str,
    ) -> str:
        heading = "CẢNH BÁO NGUY CƠ NGẬP" if event_type != "recovery" else "TRẠNG THÁI ĐÃ HẠ MỨC"

        def fmt(value: float | None) -> str:
            return "Đang khởi động" if value is None else f"{value:.1f} cm"

        return "\n".join(
            [
                "[MÔ PHỎNG THỬ NGHIỆM]",
                "",
                heading,
                f"Trạng thái: {ALERT_LABELS[alert_level]}",
                f"Dự báo 15 phút: {fmt(forecasts.get(15))}",
                f"Dự báo 30 phút: {fmt(forecasts.get(30))}",
                f"Mực nước hiện tại: {features.get('water_level_cm', 0.0):.1f} cm",
                f"Ngưỡng cảnh báo: {station['warning_level_cm']:.1f} cm",
                f"Mức tràn: {station['overflow_level_cm']:.1f} cm",
                f"Tốc độ dâng 2 phút: {features.get('water_rise_2m_cm', features.get('water_rise_5m_cm', 0.0)):+.1f} cm",
                f"Nguyên nhân: {main_factor}",
                f"Thời gian đo: {timestamp}",
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
        values = [float(features.get("water_level_cm", 0.0))]
        values.extend(float(value) for value in forecasts.values() if value is not None)
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

        if current == 2 and event_type is None:
            last_raw = state.get("last_danger_alert_at")
            last = _parse_iso(last_raw) if last_raw else None
            if last is None or delivery_now - last >= timedelta(minutes=self.settings.reminder_minutes):
                event_type = "reminder"

        if event_type in {"escalation", "reminder"} and current == 2:
            state["last_danger_alert_at"] = delivery_now.isoformat()
        state["alert_level"] = current
        self.db.set_state(state_key, state)

        if event_type is None:
            return current, None
        message = self.build_message(
            timestamp, forecasts, features, station, current, main_factor, event_type
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
            "[MÔ PHỎNG THỬ NGHIỆM]\n\nTin nhắn kiểm tra Telegram và email.",
        )


class DeliveryWorker:
    def __init__(
        self,
        db: MiniFloodDatabase,
        telegram_sender: Sender = send_telegram,
        email_sender: Sender = send_email,
    ):
        self.db = db
        self.senders = {"telegram": telegram_sender, "email": email_sender}

    def process_due(self) -> int:
        processed = 0
        for item in self.db.due_deliveries():
            sender = self.senders.get(item["channel"])
            if sender is None:
                ok, error = False, f"Kênh không hỗ trợ: {item['channel']}"
            else:
                ok, error = sender(item["message"])
            self.db.update_delivery(int(item["id"]), ok, error)
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
