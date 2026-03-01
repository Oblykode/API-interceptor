"""Auxiliary operational routes."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter

from app.core.config import get_settings
from app.domain.models import ApiEnvelope, BrowserLaunchResult

router = APIRouter(prefix="/action", tags=["actions"])


@router.post("/launch_browser", response_model=ApiEnvelope[BrowserLaunchResult])
async def launch_browser() -> ApiEnvelope[BrowserLaunchResult]:
    settings = get_settings()
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ]
    browser = next((path for path in candidates if path.exists()), None)
    if browser is None:
        return ApiEnvelope(
            ok=False,
            error="Chrome or Edge not found",
            data=BrowserLaunchResult(success=False, message="Chrome or Edge not found"),
        )

    user_data_dir = Path(tempfile.gettempdir()) / "api_interceptor_browser_profile"
    user_data_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(browser),
        f"--proxy-server={settings.proxy_host}:{settings.proxy_port}",
        "--ignore-certificate-errors",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "http://example.com",
    ]
    try:
        subprocess.Popen(cmd)
    except Exception as exc:  # pragma: no cover - platform-specific branch
        message = str(exc)
        return ApiEnvelope(
            ok=False,
            error=message,
            data=BrowserLaunchResult(success=False, message=message),
        )

    return ApiEnvelope(data=BrowserLaunchResult(success=True, message=f"Launched {browser.name}"))
