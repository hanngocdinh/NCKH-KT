from __future__ import annotations

import asyncio
import threading
from typing import Any
from .notification_settings import load_notification_config


class TelemetryBroadcaster:
    """Quản lý đăng ký và phát sự kiện dữ liệu đo thời gian thực (Pub/Sub).
    
    Hỗ trợ phát đa kênh tới các client SSE (Server-Sent Events) và WebSocket.
    """

    def __init__(self, queue_size: int | None = None) -> None:
        self._subscribers: dict[asyncio.Queue, asyncio.AbstractEventLoop] = {}
        self._lock = threading.RLock()
        self.queue_size = queue_size or load_notification_config().stream_queue_size

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self.queue_size)
        with self._lock:
            self._subscribers[queue] = asyncio.get_running_loop()
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subscribers.pop(queue, None)

    @staticmethod
    def _put(queue, event):
        if queue.full():
            queue.get_nowait()
            event = {**event, "resync_required": True}
        queue.put_nowait(event)

    def publish_sync(self, event: dict[str, Any]) -> None:
        """Phát sự kiện từ hàm đồng bộ (như service.ingest)."""
        with self._lock:
            subscribers = list(self._subscribers.items())
        for q, loop in subscribers:
            try:
                loop.call_soon_threadsafe(self._put, q, event)
            except RuntimeError:
                with self._lock:
                    self._subscribers.pop(q, None)

    async def publish(self, event: dict[str, Any]) -> None:
        """Phát sự kiện từ coroutine bất đồng bộ."""
        self.publish_sync(event)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)
