"""FastAPI server composition and lifecycle wiring."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.actions import router as actions_router
from app.api.routes.config import router as config_router
from app.api.routes.flows import router as flows_router
from app.api.routes.ws import router as ws_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.domain.models import ProxyConfig
from app.state.repository import SQLiteRepository
from app.state.store import InterceptionStore
from app.transport.ws_manager import WebSocketManager


async def _cleanup_loop(store: InterceptionStore, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=60.0)
        except asyncio.TimeoutError:
            await store.cleanup()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    logger = get_logger("app.api.server")

    repository = SQLiteRepository(settings.sqlite_path)
    await repository.init()
    config = ProxyConfig(
        intercept_enabled=settings.intercept_enabled_default,
        intercept_all=settings.intercept_all_default,
        target_ips=settings.target_ips,
        max_flows_memory=settings.max_flows_memory,
        flow_retention_minutes=settings.flow_retention_minutes,
        poll_interval_s=settings.poll_interval_s,
        max_wait_s=settings.max_wait_s,
        log_traffic=settings.log_traffic,
    )
    store = InterceptionStore(repository, config)
    await store.start()

    ws_manager = WebSocketManager(
        queue_size=settings.ws_client_queue_size,
        heartbeat_s=settings.ws_heartbeat_s,
    )
    store.subscribe(ws_manager.broadcast)
    await ws_manager.start()

    stop_event = asyncio.Event()
    cleanup_task = asyncio.create_task(_cleanup_loop(store, stop_event))

    app.state.settings = settings
    app.state.repository = repository
    app.state.store = store
    app.state.ws_manager = ws_manager
    app.state.cleanup_stop = stop_event
    app.state.cleanup_task = cleanup_task
    logger.info("Application startup complete")

    try:
        yield
    finally:
        logger.info("Application shutdown started")
        stop_event.set()
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        await ws_manager.shutdown()
        await repository.close()
        logger.info("Application shutdown complete")


app = FastAPI(
    title="API Interceptor",
    version="2.0.0",
    description="Production-grade HTTP interception server",
    lifespan=lifespan,
)

app.include_router(ws_router)
app.include_router(config_router, prefix="/api")
app.include_router(flows_router, prefix="/api")
app.include_router(actions_router, prefix="/api")

root_dir = Path(__file__).resolve().parents[2]
gui_dir = root_dir / "gui"
static_dir = gui_dir / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(gui_dir / "index.html")


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "service": "api-interceptor"}
