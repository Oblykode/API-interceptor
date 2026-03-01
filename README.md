# API Interceptor

Production-oriented HTTP/HTTPS interception stack with:
- mitmproxy addon pipeline
- FastAPI backend (REST + WebSocket)
- sequential interception queue (head-only request decision)
- SQLite-backed flow persistence
- modular frontend JavaScript

## Architecture

- `app/proxy/interceptor.py`: mitmproxy addon entrypoint
- `app/proxy/pipeline.py`: request/response interception pipeline
- `app/state/store.py`: queue/state lifecycle service
- `app/state/repository.py`: SQLite persistence
- `app/transport/ws_manager.py`: resilient WebSocket fanout
- `app/api/server.py`: FastAPI app composition
- `gui/index.html` + `gui/static/app.js`: UI

## Requirements

- Python 3.11+
- Windows PowerShell (for `smoke_test.ps1`)
- Dependencies from `requirements.txt` (includes `mitmproxy`, `fastapi`, `uvicorn`)

## Setup

Recommended:
```bat
setup.bat
```

Manual:
```bash
python -m pip install -r requirements.txt
```

## Run Modes

The app has 3 modes:

- `python main.py gui` -> API + UI only
- `python main.py proxy` -> proxy only
- `python main.py all` -> API + UI + proxy

If you run `python main.py` without args, it starts `gui` mode only.

## Check Active Host/Ports

Your effective values come from `.env` (if present) plus defaults:
```bash
python -c "from app.core.config import get_settings as g; s=g(); print('UI=',s.ui_host,s.ui_port,'PROXY=',s.proxy_host,s.proxy_port)"
```

## Demo On Your Laptop (Firefox)

1. Start both services:
```bash
python main.py all
```

2. In Firefox -> `Settings` -> `Network Settings` -> `Manual proxy configuration`:
- HTTP Proxy = `PROXY_HOST`
- Port = `PROXY_PORT`
- Enable proxy for HTTPS too

3. Open UI at `http://UI_HOST:UI_PORT`.

4. In proxied Firefox, open `http://mitm.it` and install the mitmproxy certificate to capture HTTPS.

5. Browse to:
- `http://example.com`
- `https://httpbin.org/get`

6. Confirm requests appear in UI flow history.

## Testing

Run all tests (unit + smoke):
```bat
run_tests.bat
```

Run only smoke test:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\smoke_test.ps1
```

Use smoke test against already-running services:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\smoke_test.ps1 -UseExistingServer
```

## API Contract

All REST responses use:
```json
{"ok": true, "data": {...}, "error": null}
```

Main endpoints:
- `GET /health`
- `GET /api/config`
- `PUT /api/config`
- `POST /api/config/target_ips`
- `GET /api/config/info`
- `GET /api/flows`
- `GET /api/flows/queue`
- `GET /api/flows/{flow_id}`
- `POST /api/flows`
- `PUT /api/flows/{flow_id}/response`
- `POST /api/flows/{flow_id}/request/decision`
- `GET /api/flows/{flow_id}/request/decision`
- `POST /api/flows/{flow_id}/response/decision`
- `GET /api/flows/{flow_id}/response/decision`
- `POST /api/flows/{flow_id}/complete`
- `POST /api/flows/{flow_id}/drop`
- `POST /api/flows/clear`
- `POST /api/launch_browser`
- `GET /ws`

## WebSocket Events

- `init`
- `config.updated`
- `flow.created`
- `flow.updated`
- `flow.completed`
- `flow.dropped`
- `queue.updated`
- `flows.cleared`
- `ping`
- `error`

## Configuration Notes

Common `.env` keys:
- `UI_HOST`, `UI_PORT`
- `PROXY_HOST`, `PROXY_PORT`
- `INTERCEPT_ENABLED_DEFAULT`, `INTERCEPT_ALL_DEFAULT`
- `TARGET_IPS`, `IGNORED_HOSTS`
- `MAX_FLOWS_MEMORY`, `FLOW_RETENTION_MINUTES`
- `SQLITE_PATH`
- `LOG_LEVEL`, `LOG_TRAFFIC`

Default ignored host includes `detectportal.firefox.com` to reduce browser noise.

## Troubleshooting

### "Proxy server is refusing connections"

Check that proxy mode is actually running and the browser is using the same host/port:
```bash
python main.py proxy
```

Then verify listener:
```powershell
netstat -ano | findstr :8081
```

(Replace `8081` with your configured `PROXY_PORT`.)

### `[WinError 10048] ... address already in use`

Another process is using the proxy port. Either stop that process or change `PROXY_PORT` in `.env`.

### `can't open file ... main,py`

Run with a dot:
```bash
python main.py
```

not `main,py`.

### Flows not showing (except smoke test)

- Ensure browser proxy is set for both HTTP and HTTPS.
- Ensure you are browsing with the proxied browser profile.
- Check current intercept scope in UI (`intercept_all`, `target_ips`).
- Confirm host is not in `IGNORED_HOSTS`.

### HTTPS requests not captured

Install and trust mitmproxy cert from `http://mitm.it` in the proxied browser.
See also: `docs/HTTPS_SETUP.md`.

## Additional Docs

- `docs/PROJECT_OVERVIEW.md`
- `docs/HTTPS_SETUP.md`

## License

MIT License
