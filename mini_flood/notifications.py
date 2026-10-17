from __future__ import annotations

import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Callable

import requests

from .config import MiniFloodSettings
from .db import MiniFloodDatabase


Sender = Callable[[str], tuple[bool, str]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
        predictions: dict,
        features: dict[str, float],
        main_factor: str,
        event_type: str,
    ) -> str:
        label_15 = predictions["15m"]["risk_label"]
        label_30 = predictions["30m"]["risk_label"]
        heading = "CẢNH BÁO NGUY CƠ NGẬP" if event_type != "recovery" else "TRẠNG THÁI ĐÃ AN TOÀN"
        return "\n".join(
            [
                "[MÔ PHỎNG THỬ NGHIỆM]",
                "",
                heading,
                f"Dự báo 15 phút: {label_15}",
                f"Dự báo 30 phút: {label_30}",
                f"Mực nước hiện tại: {features['water_level_cm']:.1f} cm",
                f"Tốc độ dâng 5 phút: {features['water_rise_5m_cm']:+.1f} cm",
                f"Nguyên nhân: {main_factor}",
                f"Thời gian đo: {timestamp}",
            ]
        )

    def evaluate(
        self,
        telemetry_id: int | None,
        device_id: str,
        timestamp: str,
        predictions: dict,
        features: dict[str, float],
        main_factor: str,
    ) -> int | None:
        state_key = f"alert_state:{device_id}"
        state = self.db.get_state(
            state_key,
            {"risk_level": 0, "safe_streak": 0, "last_danger_alert_at": None},
        )
        previous = int(state.get("risk_level", 0))
        current = max(int(predictions["15m"]["risk_level"]), int(predictions["30m"]["risk_level"]))
        now = _now()
        event_type: str | None = None

        if current > previous:
            event_type = "escalation"
        elif current == 2:
            last_raw = state.get("last_danger_alert_at")
            last = datetime.fromisoformat(last_raw) if last_raw else None
            if last is None or now - last >= timedelta(minutes=self.settings.reminder_minutes):
                event_type = "reminder"

        if current == 0:
            state["safe_streak"] = int(state.get("safe_streak", 0)) + 1
            if previous > 0 and state["safe_streak"] >= 2:
                event_type = "recovery"
                state["risk_level"] = 0
        else:
            state["safe_streak"] = 0
            state["risk_level"] = current

        if event_type in {"escalation", "reminder"} and current == 2:
            state["last_danger_alert_at"] = now.isoformat()
        self.db.set_state(state_key, state)

        if event_type is None:
            return None
        message = self.build_message(timestamp, predictions, features, main_factor, event_type)
        event_key = f"{device_id}:{telemetry_id}:{event_type}:{current}"
        return self.db.enqueue_alert(
            telemetry_id, device_id, event_key, event_type, current, message
        )

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
