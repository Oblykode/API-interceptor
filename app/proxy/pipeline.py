"""Interception pipeline orchestration for mitmproxy hooks."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional
from urllib.parse import urlsplit

from mitmproxy import http

from app.core.config import Settings
from app.domain.models import PacketMessage, RequestDecisionIn, ResponseDecisionIn
from app.domain.protocols import PluginHook
from app.proxy.client import UIClient
from app.proxy.utils import apply_headers, serialize_request, serialize_response


class InterceptionPipeline:

    def __init__(
        self,
        client: UIClient,
        settings: Settings,
        logger: logging.Logger,
        plugins: Optional[list[PluginHook]] = None,
    ) -> None:
        self._client = client
        self._settings = settings
        self._logger = logger
        self._plugins = plugins or []
        self._sequential_lock = asyncio.Lock()

    async def handle_request(self, flow: http.HTTPFlow) -> None:
        packet = serialize_request(flow)
        if self._is_ignored_request(packet):
            flow.resume()
            return
        packet = await self._run_before_request_capture(flow.id, packet)
        await self._client.upsert_flow(flow.id, packet.model_dump(mode="json"))
        flow.metadata["tracked"] = True

        cfg = await self._client.get_config()
        if not cfg.get("intercept_enabled", True):
            flow.resume()
            return
        if not self._should_intercept(packet, cfg):
            flow.resume()
            return

        async with self._sequential_lock:
            flow.intercept()
            decision = await self._wait_for_decision(flow.id, stage="request")
            if not decision:
                flow.resume()
                return

            action = str(decision.get("action", "forward")).lower()
            if action == "drop":
                if flow.killable:
                    flow.kill()
                else:
                    flow.resume()
                await self._client.mark_dropped(flow.id)
                await self._run_on_finalized(flow.id, "dropped")
                return

            decision_obj = RequestDecisionIn.model_validate(decision)
            decision_obj = await self._run_before_request_forward(flow.id, decision_obj)
            await self._apply_request_decision(flow, decision_obj.model_dump(mode="json"))
            flow.metadata["intercept_response"] = bool(decision_obj.intercept_response)
            flow.resume()

    async def handle_response(self, flow: http.HTTPFlow) -> None:
        if flow.response is None:
            return
        if not flow.metadata.get("tracked"):
            return

        response_packet = serialize_response(flow.response)
        await self._run_after_response_capture(flow.id, response_packet)
        await self._client.attach_response(flow.id, response_packet.model_dump(mode="json"))

        if not flow.metadata.get("intercept_response"):
            await self._client.complete_flow(flow.id)
            await self._run_on_finalized(flow.id, "completed")
            return

        async with self._sequential_lock:
            flow.intercept()
            decision = await self._wait_for_decision(flow.id, stage="response")
            if not decision:
                flow.resume()
                return

            action = str(decision.get("action", "forward")).lower()
            if action == "drop":
                if flow.killable:
                    flow.kill()
                else:
                    flow.resume()
                await self._client.mark_dropped(flow.id)
                await self._run_on_finalized(flow.id, "dropped")
                return

            decision_obj = ResponseDecisionIn.model_validate(decision)
            decision_obj = await self._run_before_response_forward(flow.id, decision_obj)
            await self._apply_response_decision(flow, decision_obj.model_dump(mode="json"))
            await self._client.complete_flow(flow.id)
            await self._run_on_finalized(flow.id, "completed")
            flow.resume()

    async def _wait_for_decision(self, flow_id: str, *, stage: str) -> Optional[dict[str, Any]]:
        deadline = time.monotonic() + self._settings.max_wait_s
        while time.monotonic() < deadline:
            if stage == "request":
                decision = await self._client.take_request_decision(flow_id)
            else:
                decision = await self._client.take_response_decision(flow_id)
            if decision:
                return decision
            await asyncio.sleep(self._settings.poll_interval_s)
        return None

    def _should_intercept(self, request: PacketMessage, cfg: dict[str, Any]) -> bool:
        if cfg.get("intercept_all", False):
            return True
        target_ips = cfg.get("target_ips", [])
        if not target_ips:
            return False
        server_ip = request.server_ip or ""
        host = request.url.split("/")[2] if "://" in request.url else request.url
        host = host.split(":")[0]
        return server_ip in target_ips or host in target_ips

    def _is_ignored_request(self, request: PacketMessage) -> bool:
        ignored = set(self._settings.ignored_hosts)
        if not ignored:
            return False
        try:
            parsed = urlsplit(request.url)
            host = (parsed.hostname or "").lower()
        except Exception:
            host = ""
        server_ip = (request.server_ip or "").lower()
        return host in ignored or server_ip in ignored

    async def _apply_request_decision(self, flow: http.HTTPFlow, decision: dict[str, Any]) -> None:
        if decision.get("method"):
            flow.request.method = str(decision["method"])
        if decision.get("url"):
            flow.request.url = str(decision["url"])
        if decision.get("headers_raw") is not None:
            apply_headers(flow.request, str(decision["headers_raw"]))
        if decision.get("body_text") is not None:
            flow.request.text = str(decision["body_text"])

    async def _apply_response_decision(self, flow: http.HTTPFlow, decision: dict[str, Any]) -> None:
        if flow.response is None:
            return
        if decision.get("status_code") is not None:
            flow.response.status_code = int(decision["status_code"])
        if decision.get("reason") is not None:
            flow.response.reason = str(decision["reason"])
        if decision.get("headers_raw") is not None:
            apply_headers(flow.response, str(decision["headers_raw"]))
        if decision.get("body_text") is not None:
            flow.response.text = str(decision["body_text"])

    async def _run_before_request_capture(self, flow_id: str, packet: PacketMessage) -> PacketMessage:
        current = packet
        for plugin in self._plugins:
            try:
                current = await plugin.before_request_capture(flow_id, current)
            except Exception as exc:
                self._logger.warning("Plugin before_request_capture failed", extra={"flow_id": flow_id, "error": str(exc)})
        return current

    async def _run_after_response_capture(self, flow_id: str, packet: PacketMessage) -> None:
        for plugin in self._plugins:
            try:
                await plugin.after_response_capture(flow_id, packet)
            except Exception as exc:
                self._logger.warning("Plugin after_response_capture failed", extra={"flow_id": flow_id, "error": str(exc)})

    async def _run_before_request_forward(self, flow_id: str, decision: RequestDecisionIn) -> RequestDecisionIn:
        current = decision
        for plugin in self._plugins:
            try:
                current = await plugin.before_request_forward(flow_id, current)
            except Exception as exc:
                self._logger.warning("Plugin before_request_forward failed", extra={"flow_id": flow_id, "error": str(exc)})
        return current

    async def _run_before_response_forward(self, flow_id: str, decision: ResponseDecisionIn) -> ResponseDecisionIn:
        current = decision
        for plugin in self._plugins:
            try:
                current = await plugin.before_response_forward(flow_id, current)
            except Exception as exc:
                self._logger.warning("Plugin before_response_forward failed", extra={"flow_id": flow_id, "error": str(exc)})
        return current

    async def _run_on_finalized(self, flow_id: str, status: str) -> None:
        for plugin in self._plugins:
            try:
                await plugin.on_flow_finalized(flow_id, status)
            except Exception as exc:
                self._logger.warning("Plugin on_flow_finalized failed", extra={"flow_id": flow_id, "error": str(exc)})
