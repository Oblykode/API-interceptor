"""Compatibility constants exported from centralized settings."""

from __future__ import annotations

from app.core.config import get_settings

_settings = get_settings()

TARGET_IPS = _settings.target_ips
INTERCEPT_ALL = _settings.intercept_all_default
UI_BASE_URL = _settings.ui_base_url
PROXY_HOST = _settings.proxy_host
PROXY_PORT = _settings.proxy_port
POLL_INTERVAL_S = _settings.poll_interval_s
MAX_WAIT_S = _settings.max_wait_s

