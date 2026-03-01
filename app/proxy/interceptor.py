"""Mitmproxy addon entrypoint using the production interception pipeline."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mitmproxy import http


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.proxy.client import UIClient
from app.proxy.pipeline import InterceptionPipeline


class AppInterceptor:

    def __init__(self) -> None:
        self._settings = get_settings()
        setup_logging(self._settings.log_level)
        self._logger = get_logger("app.proxy.interceptor")
        self._client = UIClient(base_url=self._settings.ui_base_url)
        self._pipeline = InterceptionPipeline(
            client=self._client,
            settings=self._settings,
            logger=self._logger,
            plugins=[],
        )

    async def request(self, flow: http.HTTPFlow) -> None:
        try:
            await self._pipeline.handle_request(flow)
        except Exception as exc:
            self._logger.error("Request pipeline failed", extra={"flow_id": flow.id, "error": str(exc)})
            flow.resume()

    async def response(self, flow: http.HTTPFlow) -> None:
        try:
            await self._pipeline.handle_response(flow)
        except Exception as exc:
            self._logger.error("Response pipeline failed", extra={"flow_id": flow.id, "error": str(exc)})
            flow.resume()

    def done(self) -> None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._client.close())
            else:
                loop.run_until_complete(self._client.close())
        except Exception:
            pass

addons = [AppInterceptor()]
