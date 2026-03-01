"""HTTP client used by mitmproxy addon to communicate with API server."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger


class UIClient:
    """Resilient API client with retry/backoff."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.ui_base_url or "http://127.0.0.1:8082").rstrip("/")
        self._retry_count = settings.api_retry_count
        self._retry_backoff_s = settings.api_retry_backoff_s
        self._client = httpx.AsyncClient(timeout=settings.api_request_timeout_s)
        self._logger = get_logger("app.proxy.client")

    async def close(self) -> None:
        await self._client.aclose()

    async def get_config(self) -> dict[str, Any]:
        data = await self._request_json("GET", "/api/config")
        return data if isinstance(data, dict) else {"intercept_enabled": True}

    async def upsert_flow(self, flow_id: str, request_payload: dict[str, Any]) -> None:
        await self._request_json("POST", "/api/flows", json={"id": flow_id, "request": request_payload})

    async def attach_response(self, flow_id: str, response_payload: dict[str, Any]) -> None:
        await self._request_json("PUT", f"/api/flows/{flow_id}/response", json={"response": response_payload})

    async def complete_flow(self, flow_id: str) -> None:
        await self._request_json("POST", f"/api/flows/{flow_id}/complete")

    async def mark_dropped(self, flow_id: str) -> None:
        await self._request_json("POST", f"/api/flows/{flow_id}/drop")

    async def take_request_decision(self, flow_id: str) -> Optional[dict[str, Any]]:
        data = await self._request_json("GET", f"/api/flows/{flow_id}/request/decision")
        if isinstance(data, dict):
            return data.get("decision")
        return None

    async def take_response_decision(self, flow_id: str) -> Optional[dict[str, Any]]:
        data = await self._request_json("GET", f"/api/flows/{flow_id}/response/decision")
        if isinstance(data, dict):
            return data.get("decision")
        return None

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base_url}{path}"
        attempt = 0
        last_error: Exception | None = None
        while attempt <= self._retry_count:
            try:
                response = await self._client.request(method, url, **kwargs)
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict) and "ok" in payload:
                    if not payload.get("ok", False):
                        return None
                    return payload.get("data")
                return payload
            except Exception as exc:
                last_error = exc
                if attempt >= self._retry_count:
                    break
                await asyncio.sleep(self._retry_backoff_s * (2**attempt))
                attempt += 1
        if last_error is not None:
            self._logger.warning("API request failed", extra={"method": method, "path": path, "error": str(last_error)})
        return None

