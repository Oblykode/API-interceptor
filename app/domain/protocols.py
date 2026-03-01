"""Protocols for middleware and plugin extension points."""

from __future__ import annotations

from typing import Protocol

from .models import PacketMessage, RequestDecisionIn, ResponseDecisionIn


class PluginHook(Protocol):
    """Plugin extension hooks."""

    async def before_request_capture(self, flow_id: str, request: PacketMessage) -> PacketMessage:
        ...

    async def before_request_forward(self, flow_id: str, decision: RequestDecisionIn) -> RequestDecisionIn:
        ...

    async def after_response_capture(self, flow_id: str, response: PacketMessage) -> None:
        ...

    async def before_response_forward(self, flow_id: str, decision: ResponseDecisionIn) -> ResponseDecisionIn:
        ...

    async def on_flow_finalized(self, flow_id: str, status: str) -> None:
        ...

