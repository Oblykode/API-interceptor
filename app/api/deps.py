"""Shared dependency helpers for API routes."""

from __future__ import annotations

from fastapi import Request

from app.core.config import Settings
from app.state.store import InterceptionStore
from app.transport.ws_manager import WebSocketManager


def get_store(request: Request) -> InterceptionStore:
    return request.app.state.store


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_ws_manager(request: Request) -> WebSocketManager:
    return request.app.state.ws_manager

