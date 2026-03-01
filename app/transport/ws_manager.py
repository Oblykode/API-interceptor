"""Resilient websocket manager with queue backpressure handling."""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.core.logging import get_logger
from app.domain.models import WsEvent, WsEventType


@dataclass
class _ClientSession:
    queue: asyncio.Queue[dict]
    sender_task: asyncio.Task[None]
    last_pong: float


class WebSocketManager:
    """Manages active websocket connections and fan-out delivery."""

    def __init__(self, queue_size: int = 200, heartbeat_s: float = 20.0) -> None:
        self._queue_size = queue_size
        self._heartbeat_s = heartbeat_s
        self._clients: dict[WebSocket, _ClientSession] = {}
        self._lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._logger = get_logger("app.transport.ws")

    async def start(self) -> None:
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def shutdown(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
        async with self._lock:
            sockets = list(self._clients.keys())
        for socket in sockets:
            await self.disconnect(socket)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=self._queue_size)
        sender = asyncio.create_task(self._sender(websocket, queue))
        session = _ClientSession(queue=queue, sender_task=sender, last_pong=time.monotonic())
        async with self._lock:
            self._clients[websocket] = session
        self._logger.info("WebSocket connected", extra={"clients": len(self._clients)})

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            session = self._clients.pop(websocket, None)
        if session is None:
            return
        session.sender_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await session.sender_task
        if websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await websocket.close()
        self._logger.info("WebSocket disconnected", extra={"clients": len(self._clients)})

    async def mark_pong(self, websocket: WebSocket) -> None:
        async with self._lock:
            session = self._clients.get(websocket)
            if session:
                session.last_pong = time.monotonic()

    async def send_personal(self, websocket: WebSocket, event: WsEvent) -> None:
        payload = event.model_dump(mode="json")
        async with self._lock:
            session = self._clients.get(websocket)
        if session is None:
            return
        await self._enqueue(session, payload)

    async def broadcast(self, event: WsEvent) -> None:
        payload = event.model_dump(mode="json")
        async with self._lock:
            sessions = list(self._clients.values())
        await asyncio.gather(*(self._enqueue(session, payload) for session in sessions), return_exceptions=True)

    async def _enqueue(self, session: _ClientSession, payload: dict) -> None:
        try:
            session.queue.put_nowait(payload)
            return
        except asyncio.QueueFull:
            pass

        # Backpressure: drop oldest non-critical payload and enqueue newest.
        with contextlib.suppress(asyncio.QueueEmpty):
            session.queue.get_nowait()
        with contextlib.suppress(asyncio.QueueFull):
            session.queue.put_nowait(payload)

    async def _sender(self, websocket: WebSocket, queue: asyncio.Queue[dict]) -> None:
        try:
            while True:
                payload = await queue.get()
                await websocket.send_json(payload)
        except (WebSocketDisconnect, RuntimeError):
            return
        except asyncio.CancelledError:
            return

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_s)
            now = time.monotonic()
            stale: list[WebSocket] = []
            async with self._lock:
                sockets = list(self._clients.items())
            for socket, session in sockets:
                if now - session.last_pong > self._heartbeat_s * 3:
                    stale.append(socket)
                    continue
                event = WsEvent(event=WsEventType.PING, data={"ts": now})
                await self._enqueue(session, event.model_dump(mode="json"))
            for socket in stale:
                await self.disconnect(socket)

