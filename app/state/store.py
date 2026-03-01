"""Thread-safe interception state service."""

from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from app.core.logging import get_logger
from app.domain.models import (
    DecisionPayload,
    DecisionStage,
    FlowRecord,
    FlowStatus,
    FlowSummary,
    PacketMessage,
    ProxyConfig,
    QueueState,
    RequestDecisionIn,
    ResponseDecisionIn,
    WsEvent,
    WsEventType,
)
from app.state.repository import SQLiteRepository

EventSubscriber = Callable[[WsEvent], Awaitable[None]]


class InterceptionStore:

    def __init__(self, repository: SQLiteRepository, config: ProxyConfig) -> None:
        self._repository = repository
        self._config = config
        self._lock = asyncio.Lock()
        self._flows: OrderedDict[str, FlowRecord] = OrderedDict()
        self._queue: deque[str] = deque()
        self._subscribers: list[EventSubscriber] = []
        self._logger = get_logger("app.state.store")

    async def start(self) -> None:
        recent = await self._repository.list_flows(limit=self._config.max_flows_memory)
        async with self._lock:
            for flow in reversed(recent):
                self._flows[flow.id] = flow
            for flow in reversed(recent):
                if flow.status == FlowStatus.PENDING_REQUEST:
                    self._queue.append(flow.id)

    def subscribe(self, callback: EventSubscriber) -> None:
        self._subscribers.append(callback)

    async def get_config(self) -> ProxyConfig:
        async with self._lock:
            return self._config.model_copy(deep=True)

    async def update_config(self, config: ProxyConfig) -> ProxyConfig:
        async with self._lock:
            self._config = config
            snapshot = self._config.model_copy(deep=True)
        await self._publish(WsEventType.CONFIG_UPDATED, snapshot.model_dump(mode="json"))
        return snapshot

    async def upsert_request(self, flow_id: str, request: PacketMessage) -> FlowRecord:
        created = False
        queue_changed = False
        async with self._lock:
            record = self._flows.get(flow_id)
            if record is None:
                record = await self._repository.get_flow(flow_id)

            if record is None:
                created = True
                record = FlowRecord(id=flow_id, request=request, status=FlowStatus.PENDING_REQUEST)
            else:
                record.request = request
                record.updated_at = datetime.now(timezone.utc)
                if record.status in (FlowStatus.COMPLETED, FlowStatus.DROPPED):
                    record.status = FlowStatus.PENDING_REQUEST
                    record.response = None
                if record.status != FlowStatus.PENDING_REQUEST:
                    record.status = FlowStatus.PENDING_REQUEST

            if flow_id not in self._queue:
                self._queue.append(flow_id)
                queue_changed = True

            self._set_cache(record)
            await self._repository.upsert_flow(record)
            summary = self._to_summary(record)
            queue_state = self._queue_state()

        await self._publish(WsEventType.FLOW_CREATED if created else WsEventType.FLOW_UPDATED, summary.model_dump(mode="json"), flow_id=flow_id)
        if queue_changed:
            await self._publish(WsEventType.QUEUE_UPDATED, queue_state.model_dump(mode="json"))
        return record

    async def attach_response(self, flow_id: str, response: PacketMessage) -> FlowRecord:
        async with self._lock:
            record = self._flows.get(flow_id)
            if record is None:
                record = await self._repository.get_flow(flow_id)
            if record is None:
                record = FlowRecord(id=flow_id, request=PacketMessage(method="GET", url="<unknown>"))

            record.response = response
            record.status = FlowStatus.PENDING_RESPONSE
            record.updated_at = datetime.now(timezone.utc)
            self._set_cache(record)
            await self._repository.upsert_flow(record)
            summary = self._to_summary(record)

        await self._publish(WsEventType.FLOW_UPDATED, summary.model_dump(mode="json"), flow_id=flow_id)
        return record

    async def mark_completed(self, flow_id: str) -> None:
        await self._set_final_status(flow_id, FlowStatus.COMPLETED, WsEventType.FLOW_COMPLETED)

    async def mark_dropped(self, flow_id: str) -> None:
        await self._set_final_status(flow_id, FlowStatus.DROPPED, WsEventType.FLOW_DROPPED)

    async def list_flows(
        self,
        *,
        limit: int = 100,
        search: Optional[str] = None,
        method: Optional[str] = None,
        status: Optional[str] = None,
        has_response: Optional[bool] = None,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
    ) -> list[FlowSummary]:
        rows = await self._repository.list_flows(
            limit=limit,
            search=search,
            method=method,
            status=status,
            has_response=has_response,
            from_ts=from_ts,
            to_ts=to_ts,
        )
        async with self._lock:
            queue_map = {flow_id: idx + 1 for idx, flow_id in enumerate(self._queue)}
        summaries: list[FlowSummary] = []
        for row in rows:
            item = self._to_summary(row)
            item.queue_position = queue_map.get(row.id)
            summaries.append(item)
        return summaries

    async def get_flow(self, flow_id: str) -> Optional[FlowRecord]:
        async with self._lock:
            cached = self._flows.get(flow_id)
            if cached is not None:
                return cached.model_copy(deep=True)
        record = await self._repository.get_flow(flow_id)
        if record is None:
            return None
        async with self._lock:
            self._set_cache(record)
        return record

    async def set_request_decision(self, flow_id: str, decision: RequestDecisionIn) -> None:
        queue_changed = False
        status_event: tuple[WsEventType, dict] | None = None
        async with self._lock:
            if not self._queue or self._queue[0] != flow_id:
                raise ValueError("Only the active queue head can be decided")

            await self._repository.set_decision(flow_id, DecisionStage.REQUEST, decision.model_dump(mode="json"))

            if decision.action.value == "drop":
                record = await self._resolve_flow(flow_id)
                if record is not None:
                    record.status = FlowStatus.DROPPED
                    record.updated_at = datetime.now(timezone.utc)
                    self._set_cache(record)
                    await self._repository.upsert_flow(record)
                    status_event = (WsEventType.FLOW_DROPPED, self._to_summary(record).model_dump(mode="json"))
                if self._queue and self._queue[0] == flow_id:
                    self._queue.popleft()
                    queue_changed = True

        if status_event:
            await self._publish(status_event[0], status_event[1], flow_id=flow_id)
        if queue_changed:
            await self._publish(WsEventType.QUEUE_UPDATED, (await self.queue_state()).model_dump(mode="json"))

    async def take_request_decision(self, flow_id: str) -> DecisionPayload:
        queue_changed = False
        decision = await self._repository.take_decision(flow_id, DecisionStage.REQUEST)
        if decision:
            async with self._lock:
                if self._queue and self._queue[0] == flow_id:
                    self._queue.popleft()
                    queue_changed = True
        if queue_changed:
            await self._publish(WsEventType.QUEUE_UPDATED, (await self.queue_state()).model_dump(mode="json"))
        return DecisionPayload(decision=decision)

    async def set_response_decision(self, flow_id: str, decision: ResponseDecisionIn) -> None:
        await self._repository.set_decision(flow_id, DecisionStage.RESPONSE, decision.model_dump(mode="json"))
        if decision.action.value == "drop":
            await self.mark_dropped(flow_id)
        else:
            await self.mark_completed(flow_id)

    async def take_response_decision(self, flow_id: str) -> DecisionPayload:
        decision = await self._repository.take_decision(flow_id, DecisionStage.RESPONSE)
        return DecisionPayload(decision=decision)

    async def queue_state(self) -> QueueState:
        async with self._lock:
            return self._queue_state()

    async def clear_history(self) -> None:
        async with self._lock:
            self._flows.clear()
            self._queue.clear()
            await self._repository.clear_all()
        await self._publish(WsEventType.FLOWS_CLEARED, {"message": "history cleared"})
        await self._publish(WsEventType.QUEUE_UPDATED, {"pending": [], "active": None})

    async def cleanup(self) -> int:
        deleted = await self._repository.cleanup_old(self._config.flow_retention_minutes)
        if deleted <= 0:
            return 0

        recent = await self._repository.list_flows(limit=self._config.max_flows_memory)
        async with self._lock:
            self._flows.clear()
            for flow in reversed(recent):
                self._flows[flow.id] = flow
            valid_ids = set(self._flows.keys())
            preserved = [flow_id for flow_id in self._queue if flow_id in valid_ids]
            pending = [
                flow_id
                for flow_id, flow in self._flows.items()
                if flow.status == FlowStatus.PENDING_REQUEST and flow_id not in preserved
            ]
            self._queue = deque(preserved + pending)
        if deleted > 0:
            self._logger.info("Cleanup removed stale flows", extra={"deleted": deleted})
        return deleted

    async def _set_final_status(self, flow_id: str, status: FlowStatus, event_type: WsEventType) -> None:
        queue_changed = False
        async with self._lock:
            record = await self._resolve_flow(flow_id)
            if record is None:
                return
            record.status = status
            record.updated_at = datetime.now(timezone.utc)
            self._set_cache(record)
            await self._repository.upsert_flow(record)
            if flow_id in self._queue:
                self._queue = deque(item for item in self._queue if item != flow_id)
                queue_changed = True
            summary = self._to_summary(record)

        await self._publish(event_type, summary.model_dump(mode="json"), flow_id=flow_id)
        if queue_changed:
            await self._publish(WsEventType.QUEUE_UPDATED, (await self.queue_state()).model_dump(mode="json"))

    async def _publish(self, event_type: WsEventType | str, payload: dict, *, flow_id: Optional[str] = None) -> None:
        event_name = event_type.value if isinstance(event_type, WsEventType) else str(event_type)
        event_id = await self._repository.append_event(flow_id, event_name, payload)
        event = WsEvent(event=event_type, event_id=event_id, data=payload)
        if not self._subscribers:
            return
        await asyncio.gather(*(subscriber(event) for subscriber in self._subscribers), return_exceptions=True)

    def _set_cache(self, record: FlowRecord) -> None:
        self._flows[record.id] = record.model_copy(deep=True)
        self._flows.move_to_end(record.id)
        while len(self._flows) > self._config.max_flows_memory:
            oldest_id, _ = self._flows.popitem(last=False)
            self._queue = deque(item for item in self._queue if item != oldest_id)

    async def _resolve_flow(self, flow_id: str) -> Optional[FlowRecord]:
        record = self._flows.get(flow_id)
        if record is not None:
            return record
        return await self._repository.get_flow(flow_id)

    def _to_summary(self, record: FlowRecord) -> FlowSummary:
        return FlowSummary(
            id=record.id,
            method=record.request.method,
            url=record.request.url,
            status=record.status,
            status_code=record.response.status_code if record.response else None,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _queue_state(self) -> QueueState:
        pending = list(self._queue)
        return QueueState(pending=pending, active=pending[0] if pending else None)
