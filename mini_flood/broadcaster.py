from __future__ import annotations

import asyncio
from typing import Any


class TelemetryBroadcaster:
    """Quản lý đăng ký và phát sự kiện dữ liệu đo thời gian thực (Pub/Sub).
    
    Hỗ trợ phát đa kênh tới các client SSE (Server-Sent Events) và WebSocket.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    def publish_sync(self, event: dict[str, Any]) -> None:
        """Phát sự kiện từ hàm đồng bộ (như service.ingest)."""
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def publish(self, event: dict[str, Any]) -> None:
        """Phát sự kiện từ coroutine bất đồng bộ."""
        async with self._lock:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


broadcaster = TelemetryBroadcaster()
