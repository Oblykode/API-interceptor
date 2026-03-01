"""Helper utilities for proxy serialization and header conversion."""

from __future__ import annotations

import json
from typing import Any

from mitmproxy import http

from app.domain.models import PacketMessage


def headers_to_raw(pairs: list[tuple[str, str]]) -> str:
    return "\n".join(f"{name}: {value}" for name, value in pairs)


def raw_to_header_pairs(raw: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for line in raw.splitlines():
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        key = name.strip()
        val = value.strip()
        if key:
            out.append((key, val))
    return out


def looks_like_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except Exception:
        return False


def safe_text(message: http.Message) -> str:
    try:
        return message.get_text(strict=False) or ""
    except Exception:
        return ""


def serialize_request(flow: http.HTTPFlow) -> PacketMessage:
    req = flow.request
    body = safe_text(req)
    server_ip = req.host_header.split(":")[0] if req.host_header else req.host
    return PacketMessage(
        method=req.method,
        url=req.pretty_url,
        http_version=req.http_version or "HTTP/1.1",
        headers_raw=headers_to_raw(list(req.headers.items(multi=True))),
        body_text=body,
        body_is_json=looks_like_json(body),
        client_ip=(flow.client_conn.address[0] if flow.client_conn and flow.client_conn.address else None),
        server_ip=server_ip,
    )


def serialize_response(resp: http.Response) -> PacketMessage:
    body = safe_text(resp)
    return PacketMessage(
        method="RESPONSE",
        url="",
        http_version=resp.http_version or "HTTP/1.1",
        headers_raw=headers_to_raw(list(resp.headers.items(multi=True))),
        body_text=body,
        body_is_json=looks_like_json(body),
        status_code=resp.status_code,
        reason=resp.reason or "",
    )


def apply_headers(message: http.Message, headers_raw: str) -> None:
    pairs = raw_to_header_pairs(headers_raw)
    fields: list[tuple[bytes, bytes]] = []
    for key, value in pairs:
        fields.append((key.encode("utf-8", "surrogateescape"), value.encode("utf-8", "surrogateescape")))
    message.headers = http.Headers(fields)

