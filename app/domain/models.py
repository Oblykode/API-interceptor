"""Pydantic models and enums for API and proxy interactions."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FlowStatus(str, Enum):
    PENDING_REQUEST = "pending_request"
    PENDING_RESPONSE = "pending_response"
    COMPLETED = "completed"
    DROPPED = "dropped"


class DecisionAction(str, Enum):
    FORWARD = "forward"
    DROP = "drop"


class DecisionStage(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"


class WsEventType(str, Enum):
    INIT = "init"
    CONFIG_UPDATED = "config.updated"
    FLOW_CREATED = "flow.created"
    FLOW_UPDATED = "flow.updated"
    FLOW_COMPLETED = "flow.completed"
    FLOW_DROPPED = "flow.dropped"
    QUEUE_UPDATED = "queue.updated"
    ERROR = "error"
    PING = "ping"
    FLOWS_CLEARED = "flows.cleared"


class PacketMessage(BaseModel):
    method: str = "GET"
    url: str = ""
    http_version: str = "HTTP/1.1"
    headers_raw: str = ""
    body_text: str = ""
    body_is_json: bool = False

    status_code: Optional[int] = None
    reason: Optional[str] = None

    client_ip: Optional[str] = None
    server_ip: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


class ProxyConfig(BaseModel):
    intercept_enabled: bool = True
    intercept_all: bool = False
    target_ips: list[str] = Field(default_factory=list)

    max_flows_memory: int = 1000
    flow_retention_minutes: int = 60

    poll_interval_s: float = 0.25
    max_wait_s: float = 60.0 * 5

    log_traffic: bool = False


class FlowRecord(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: str
    request: PacketMessage
    response: Optional[PacketMessage] = None
    status: FlowStatus = FlowStatus.PENDING_REQUEST

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FlowSummary(BaseModel):
    id: str
    method: str
    url: str
    status: FlowStatus
    status_code: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    queue_position: Optional[int] = None


class UpsertFlowIn(BaseModel):
    id: str
    request: PacketMessage


class UpsertResponseIn(BaseModel):
    response: PacketMessage


class RequestDecisionIn(BaseModel):
    action: DecisionAction
    method: Optional[str] = None
    url: Optional[str] = None
    headers_raw: Optional[str] = None
    body_text: Optional[str] = None
    intercept_response: bool = False


class ResponseDecisionIn(BaseModel):
    action: DecisionAction
    status_code: Optional[int] = None
    reason: Optional[str] = None
    headers_raw: Optional[str] = None
    body_text: Optional[str] = None


class DecisionPayload(BaseModel):
    decision: Optional[dict[str, Any]] = None


class QueueState(BaseModel):
    pending: list[str] = Field(default_factory=list)
    active: Optional[str] = None


class InitPayload(BaseModel):
    config: ProxyConfig
    queue: QueueState
    flows: list[FlowSummary]


class WsEvent(BaseModel):
    event: WsEventType | str
    event_id: Optional[int] = None
    data: Optional[Any] = None
    ts: datetime = Field(default_factory=utc_now)


class TargetIpsUpdateIn(BaseModel):
    target_ips: list[str] = Field(default_factory=list)


class BrowserLaunchResult(BaseModel):
    success: bool
    message: str


T = TypeVar("T")


class ApiEnvelope(BaseModel, Generic[T]):
    ok: bool = True
    data: Optional[T] = None
    error: Optional[str] = None
