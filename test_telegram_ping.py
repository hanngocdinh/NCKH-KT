#!/usr/bin/env python
"""Tiện ích kiểm tra kết nối Telegram Bot cho hệ thống Mini Flood AI.

Cách dùng:
    python test_telegram_ping.py
    python test_telegram_ping.py --token <BOT_TOKEN> --chat-id <CHAT_ID>
"""

from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from mini_flood.notifications import main

if __name__ == "__main__":
    sys.exit(main())
