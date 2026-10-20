"""FastAPI nhận dữ liệu ESP32 cho prototype dự báo ngập 15/30 phút.

Chạy:
    uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import threading
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from mini_flood import MiniFloodService, MiniFloodSettings
from mini_flood.schemas import ExperimentStart, TelemetryPayload, TelemetryResponse


def create_app(settings: MiniFloodSettings | None = None) -> FastAPI:
    resolved = settings or MiniFloodSettings.from_env()
    service = MiniFloodService(resolved)
    stop_event = threading.Event()

    def delivery_loop() -> None:
        while not stop_event.wait(resolved.notification_poll_seconds):
            service.delivery_worker.process_due()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        worker: threading.Thread | None = None
        if resolved.notification_worker_enabled:
            worker = threading.Thread(target=delivery_loop, name="mini-flood-alert-worker", daemon=True)
            worker.start()
        yield
        stop_event.set()
        if worker:
            worker.join(timeout=2)

    api = FastAPI(
        title="Mini Flood AI API",
        version="1.0.0",
        description="[MÔ PHỎNG THỬ NGHIỆM] Nhận telemetry và dự báo nguy cơ ngập 15/30 phút.",
        lifespan=lifespan,
    )
    api.state.service = service

    def authorize(device_key: str | None) -> None:
        if not device_key or device_key != resolved.device_api_key:
            raise HTTPException(status_code=401, detail="X-Device-Key không hợp lệ")

    @api.get("/api/v1/health")
    def health() -> dict:
        return {
            "status": "ok",
            "simulation": True,
            "model_ready": service.registry.ready,
            "model_version": service.registry.version,
            "database": service.db.counts(),
            "active_subscribers": service.broadcaster.subscriber_count,
        }

    @api.post("/api/v1/telemetry", response_model=TelemetryResponse)
    def telemetry(
        payload: TelemetryPayload,
        background_tasks: BackgroundTasks,
        x_device_key: str | None = Header(default=None, alias="X-Device-Key"),
    ) -> dict:
        authorize(x_device_key)
        result = service.ingest(payload)
        background_tasks.add_task(service.delivery_worker.process_due)
        return result

    @api.get("/api/v1/stations/{device_id}/latest")
    def latest(
        device_id: str,
        x_device_key: str | None = Header(default=None, alias="X-Device-Key"),
    ) -> dict:
        authorize(x_device_key)
        row = service.db.latest(device_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Chưa có dữ liệu cho thiết bị")
        return row

    @api.get("/api/v1/stations/{device_id}/history")
    def history(
        device_id: str,
        limit: int = Query(default=200, ge=1, le=5000),
        x_device_key: str | None = Header(default=None, alias="X-Device-Key"),
    ) -> dict:
        authorize(x_device_key)
        return {"device_id": device_id, "items": service.db.history(device_id, limit)}

    @api.post("/api/v1/notifications/test")
    def notification_test(
        device_id: str = "mini-flood-station-01",
        x_device_key: str | None = Header(default=None, alias="X-Device-Key"),
    ) -> dict:
        authorize(x_device_key)
        alert_id = service.alerts.enqueue_test(device_id)
        processed = service.delivery_worker.process_due()
        return {"queued": alert_id is not None, "alert_id": alert_id, "deliveries_processed": processed}

    @api.post("/api/v1/experiments/start")
    def start_experiment(
        request: ExperimentStart,
        x_device_key: str | None = Header(default=None, alias="X-Device-Key"),
    ) -> dict:
        authorize(x_device_key)
        state = request.model_dump()
        service.db.set_state(f"active_experiment:{request.device_id}", state)
        return {"active": True, **state}

    @api.post("/api/v1/experiments/stop")
    def stop_experiment(
        device_id: str = "mini-flood-station-01",
        x_device_key: str | None = Header(default=None, alias="X-Device-Key"),
    ) -> dict:
        authorize(x_device_key)
        service.db.set_state(
            f"active_experiment:{device_id}",
            {"experiment_id": "unassigned", "scenario": None},
        )
        return {"active": False, "device_id": device_id}

    @api.get("/api/v1/experiments/export.csv")
    def export_experiments(
        device_id: str | None = None,
        x_device_key: str | None = Header(default=None, alias="X-Device-Key"),
    ) -> StreamingResponse:
        authorize(x_device_key)
        rows = service.db.experiment_rows(device_id)
        buffer = io.StringIO()
        fields = [
            "experiment_id", "device_id", "sequence_no", "timestamp",
            "rain_interval_mm", "rain_rate_mmh", "water_level_cm", "quality_flags",
        ]
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=telemetry_experiments.csv"},
        )

    @api.get("/api/v1/stream/sse")
    async def stream_sse(
        device_id: str | None = None,
    ) -> StreamingResponse:
        """Lắng nghe dữ liệu đo mực nước và lượng mưa thời gian thực qua Server-Sent Events (SSE)."""
        queue = await service.broadcaster.subscribe()

        async def event_generator():
            try:
                yield f"event: connected\ndata: {json.dumps({'status': 'connected', 'device_id': device_id}, ensure_ascii=False)}\n\n"
                while True:
                    event = await queue.get()
                    if device_id and event.get("device_id") != device_id:
                        continue
                    payload = json.dumps(event, ensure_ascii=False)
                    yield f"event: telemetry\ndata: {payload}\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                await service.broadcaster.unsubscribe(queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
            },
        )

    @api.websocket("/api/v1/stream/ws")
    async def stream_ws(websocket: WebSocket, device_id: str | None = None):
        """Lắng nghe dữ liệu đo mực nước và lượng mưa thời gian thực qua WebSocket."""
        await websocket.accept()
        queue = await service.broadcaster.subscribe()
        try:
            await websocket.send_json({"type": "connected", "status": "ok", "device_id": device_id})
            while True:
                get_task = asyncio.create_task(queue.get())
                recv_task = asyncio.create_task(websocket.receive_text())
                done, pending = await asyncio.wait(
                    [get_task, recv_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()

                if get_task in done:
                    event = get_task.result()
                    if device_id is None or event.get("device_id") == device_id:
                        await websocket.send_json(event)
                if recv_task in done:
                    msg = recv_task.result()
                    if msg.strip().lower() == "ping":
                        await websocket.send_text("pong")
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            await service.broadcaster.unsubscribe(queue)

    return api


app = create_app()
