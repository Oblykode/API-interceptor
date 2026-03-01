# API Interceptor - Project Overview (Refactored)

## Structure

```text
API_Interceptor/
├── app/
│   ├── api/
│   │   ├── server.py
│   │   ├── deps.py
│   │   └── routes/
│   │       ├── config.py
│   │       ├── flows.py
│   │       ├── actions.py
│   │       └── ws.py
│   ├── core/
│   │   ├── config.py
│   │   └── logging.py
│   ├── domain/
│   │   ├── models.py
│   │   └── protocols.py
│   ├── proxy/
│   │   ├── interceptor.py
│   │   ├── pipeline.py
│   │   ├── client.py
│   │   └── utils.py
│   ├── state/
│   │   ├── repository.py
│   │   └── store.py
│   └── transport/
│       └── ws_manager.py
├── gui/
│   ├── index.html
│   └── static/app.js
├── tests/
├── main.py
├── config.py
└── requirements.txt
```

## Runtime Flow

1. `mitmdump` loads `app/proxy/interceptor.py`.
2. Interceptor serializes request/response and communicates with FastAPI via `app/proxy/client.py`.
3. FastAPI routes (`/api/flows/*`) persist flow state in SQLite through `app/state/repository.py`.
4. `app/state/store.py` enforces queue-head request decisions and publishes events.
5. `app/transport/ws_manager.py` broadcasts typed events to `/ws`.
6. Frontend (`gui/static/app.js`) renders queue/history, submits decisions, and polls as fallback if WS drops.

## Key Design Decisions

- Clean separation by layer (`core`, `domain`, `state`, `proxy`, `transport`, `api`).
- Envelope-based API responses: `{"ok": bool, "data": ..., "error": ...}`.
- Sequential interception queue with head-only decision enforcement.
- SQLite persistence with in-memory hot cache.
- Reconnect-capable WebSocket transport with per-client queues and heartbeat pings.
- Plugin-ready protocol hooks for future extension.

## Runtime Ports

Ports are configuration-driven. Do not assume fixed values.

Check active values:

```bash
python -c "from app.core.config import get_settings as g; s=g(); print('UI=',s.ui_host,s.ui_port,'PROXY=',s.proxy_host,s.proxy_port)"
```

Typical local `.env` in this project currently uses:
- UI/API: `127.0.0.1:8081`
- Proxy listener: `127.0.0.1:8080`

## Verification Strategy

1. API and state verification: `smoke_test.ps1`.
2. WebSocket initialization event verification: `smoke_test.ps1`.
3. Real proxy-capture verification (request sent through configured proxy and validated in flow history): `smoke_test.ps1`.
4. Manual browser demo for request forward/drop and response interception.
