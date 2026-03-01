"""Flow lifecycle and decision routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_store
from app.domain.models import (
    ApiEnvelope,
    DecisionPayload,
    FlowRecord,
    FlowSummary,
    RequestDecisionIn,
    ResponseDecisionIn,
    UpsertFlowIn,
    UpsertResponseIn,
)
from app.state.store import InterceptionStore

router = APIRouter(prefix="/flows", tags=["flows"])


@router.get("", response_model=ApiEnvelope[list[FlowSummary]])
async def list_flows(
    limit: int = Query(default=100, ge=1, le=1000),
    search: Optional[str] = None,
    method: Optional[str] = None,
    status: Optional[str] = None,
    has_response: Optional[bool] = None,
    from_ts: Optional[float] = None,
    to_ts: Optional[float] = None,
    store: InterceptionStore = Depends(get_store),
) -> ApiEnvelope[list[FlowSummary]]:
    flows = await store.list_flows(
        limit=limit,
        search=search,
        method=method,
        status=status,
        has_response=has_response,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    return ApiEnvelope(data=flows)


@router.get("/queue", response_model=ApiEnvelope[dict])
async def get_queue(store: InterceptionStore = Depends(get_store)) -> ApiEnvelope[dict]:
    queue = await store.queue_state()
    return ApiEnvelope(data=queue.model_dump(mode="json"))


@router.get("/{flow_id}", response_model=ApiEnvelope[FlowRecord])
async def get_flow(flow_id: str, store: InterceptionStore = Depends(get_store)) -> ApiEnvelope[FlowRecord]:
    record = await store.get_flow(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="flow not found")
    return ApiEnvelope(data=record)


@router.post("", response_model=ApiEnvelope[FlowRecord])
async def upsert_flow(payload: UpsertFlowIn, store: InterceptionStore = Depends(get_store)) -> ApiEnvelope[FlowRecord]:
    record = await store.upsert_request(payload.id, payload.request)
    return ApiEnvelope(data=record)


@router.put("/{flow_id}/response", response_model=ApiEnvelope[FlowRecord])
async def attach_response(
    flow_id: str,
    payload: UpsertResponseIn,
    store: InterceptionStore = Depends(get_store),
) -> ApiEnvelope[FlowRecord]:
    record = await store.attach_response(flow_id, payload.response)
    return ApiEnvelope(data=record)


@router.post("/{flow_id}/complete", response_model=ApiEnvelope[dict])
async def complete_flow(flow_id: str, store: InterceptionStore = Depends(get_store)) -> ApiEnvelope[dict]:
    await store.mark_completed(flow_id)
    return ApiEnvelope(data={"flow_id": flow_id, "status": "completed"})


@router.post("/{flow_id}/drop", response_model=ApiEnvelope[dict])
async def drop_flow(flow_id: str, store: InterceptionStore = Depends(get_store)) -> ApiEnvelope[dict]:
    await store.mark_dropped(flow_id)
    return ApiEnvelope(data={"flow_id": flow_id, "status": "dropped"})


@router.post("/{flow_id}/request/decision", response_model=ApiEnvelope[dict])
async def set_request_decision(
    flow_id: str,
    decision: RequestDecisionIn,
    store: InterceptionStore = Depends(get_store),
) -> ApiEnvelope[dict]:
    try:
        await store.set_request_decision(flow_id, decision)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ApiEnvelope(data={"flow_id": flow_id, "queued": False})


@router.get("/{flow_id}/request/decision", response_model=ApiEnvelope[DecisionPayload])
async def take_request_decision(
    flow_id: str,
    store: InterceptionStore = Depends(get_store),
) -> ApiEnvelope[DecisionPayload]:
    payload = await store.take_request_decision(flow_id)
    return ApiEnvelope(data=payload)


@router.post("/{flow_id}/response/decision", response_model=ApiEnvelope[dict])
async def set_response_decision(
    flow_id: str,
    decision: ResponseDecisionIn,
    store: InterceptionStore = Depends(get_store),
) -> ApiEnvelope[dict]:
    await store.set_response_decision(flow_id, decision)
    return ApiEnvelope(data={"flow_id": flow_id, "queued": False})


@router.get("/{flow_id}/response/decision", response_model=ApiEnvelope[DecisionPayload])
async def take_response_decision(
    flow_id: str,
    store: InterceptionStore = Depends(get_store),
) -> ApiEnvelope[DecisionPayload]:
    payload = await store.take_response_decision(flow_id)
    return ApiEnvelope(data=payload)


@router.post("/clear", response_model=ApiEnvelope[dict])
async def clear_flows(store: InterceptionStore = Depends(get_store)) -> ApiEnvelope[dict]:
    await store.clear_history()
    return ApiEnvelope(data={"cleared": True})

