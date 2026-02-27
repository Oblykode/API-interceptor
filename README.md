# API Interceptor (Refactored Architecture)

Production-oriented HTTP/HTTPS interception stack with:
- Mitmproxy addon pipeline
- FastAPI backend with REST + WebSocket
- Sequential interception queue
- SQLite-backed history and decisions
- Modular frontend JavaScript

## Run

```bash
pip install -r requirements.txt
python main.py all
```

Modes:
- `python main.py gui`
- `python main.py proxy`
- `python main.py all`

## Default Endpoints

- GUI: `http://127.0.0.1:8082` (or `UI_HOST/UI_PORT` from `.env`)
- Proxy: `127.0.0.1:8081` (or `PROXY_HOST/PROXY_PORT` from `.env`)
- Health: `GET /health`
- WebSocket: `GET /ws`

## Backend Structure

```text
app/
  api/
    server.py
    routes/
  core/
    config.py
    logging.py
  domain/
    models.py
    protocols.py
  proxy/
    interceptor.py
    pipeline.py
    client.py
    utils.py
  state/
    repository.py
    store.py
  transport/
    ws_manager.py
```

## Key API

All REST responses are envelope-based:

```json
{"ok": true, "data": {...}, "error": null}
```

Important routes:
- `GET /api/config`
- `PUT /api/config`
- `GET /api/flows`
- `GET /api/flows/{flow_id}`
- `POST /api/flows`
- `PUT /api/flows/{flow_id}/response`
- `POST /api/flows/{flow_id}/request/decision`
- `GET /api/flows/{flow_id}/request/decision`
- `POST /api/flows/{flow_id}/response/decision`
- `GET /api/flows/{flow_id}/response/decision`
- `GET /api/flows/queue`
- `POST /api/flows/clear`

## Notes

- Request decisions are queue-head enforced for robust sequential intercept behavior.
- SQLite DB path is configurable via `SQLITE_PATH` (`data/interceptor.db` by default).
- Frontend script now lives at `gui/static/app.js`.

