"""FastAPI nhận dữ liệu ESP32 cho prototype dự báo ngập 15/30 phút.

Chạy:
    uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import threading
import csv
import io
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query
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

    return api


app = create_app()
