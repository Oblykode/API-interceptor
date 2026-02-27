# API Interceptor (Refactored Architecture)

Production-grade HTTP/HTTPS interception framework featuring:
- **Mitmproxy addon pipeline** for transparent request/response interception
- **FastAPI backend** with RESTful API + WebSocket real-time updates
- **Sequential interception queue** with decision enforcement
- **SQLite persistence** for flow history and user decisions
- **Modern responsive UI** with modular JavaScript architecture

## Quick Start

### Installation
```bash
pip install -r requirements.txt
```

### Running
```bash
# Run both proxy and GUI
python main.py all

# Run components separately
python main.py gui      # GUI only
python main.py proxy    # Proxy only
```

## Configuration

Create a `.env` file in the project root (optional):
```env
# Server Configuration
UI_HOST=127.0.0.1
UI_PORT=8082

# Proxy Configuration
PROXY_HOST=127.0.0.1
PROXY_PORT=8081

# Database
SQLITE_PATH=data/interceptor.db

# Logging
LOG_LEVEL=INFO
```

## Default Endpoints

| Service | Endpoint | Description |
|---------|----------|-------------|
| **GUI** | `http://127.0.0.1:8082` | Web interface |
| **Proxy** | `127.0.0.1:8081` | MITM proxy server |
| **Health** | `GET /health` | Service health check |
| **WebSocket** | `GET /ws` | Real-time flow updates |

## Project Structure
```text
api-interceptor/
├── app/
│   ├── api/
│   │   ├── server.py           # FastAPI application
│   │   └── routes/             # API route handlers
│   ├── core/
│   │   ├── config.py           # Configuration management
│   │   └── logging.py          # Logging setup
│   ├── domain/
│   │   ├── models.py           # Data models
│   │   └── protocols.py        # Type protocols
│   ├── proxy/
│   │   ├── interceptor.py      # Mitmproxy addon
│   │   ├── pipeline.py         # Request pipeline
│   │   ├── client.py           # Proxy client
│   │   └── utils.py            # Utility functions
│   ├── state/
│   │   ├── repository.py       # Database operations
│   │   └── store.py            # In-memory state
│   └── transport/
│       └── ws_manager.py       # WebSocket manager
├── gui/
│   ├── static/
│   │   ├── app.js              # Frontend JavaScript
│   │   ├── style.css           # Styling
│   │   └── index.html          # Main page
│   └── templates/              # HTML templates
├── data/
│   └── interceptor.db          # SQLite database
├── main.py                      # Application entry point
├── requirements.txt
└── .env                        # Environment configuration
```

## API Reference

### Response Envelope

All REST API responses follow this structure:
```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

### Core Endpoints

#### Configuration
```http
GET  /api/config              # Get current configuration
PUT  /api/config              # Update configuration
```

#### Flows
```http
GET    /api/flows             # List all flows
GET    /api/flows/{flow_id}   # Get specific flow
POST   /api/flows             # Create new flow
PUT    /api/flows/{flow_id}/response  # Update flow response
GET    /api/flows/queue       # Get pending flows queue
POST   /api/flows/clear       # Clear flow history
```

#### Request Decisions
```http
POST   /api/flows/{flow_id}/request/decision   # Make request decision
GET    /api/flows/{flow_id}/request/decision   # Get request decision
```

#### Response Decisions
```http
POST   /api/flows/{flow_id}/response/decision  # Make response decision
GET    /api/flows/{flow_id}/response/decision  # Get response decision
```

### WebSocket Events

Connect to `/ws` for real-time updates:
```javascript
const ws = new WebSocket('ws://127.0.0.1:8082/ws');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // Handle: flow_created, flow_updated, decision_made, etc.
};
```

## Features

### Sequential Interception
- Queue-based request processing ensures ordered handling
- Queue-head enforcement for robust decision workflow
- Prevents race conditions in concurrent environments

### Persistent Storage
- SQLite database for flow history
- Searchable and filterable flow logs
- Decision history tracking

### Real-time Updates
- WebSocket push notifications
- Live flow status updates
- Instant UI synchronization

### Flexible Decisions
- Allow/Block requests at interception point
- Modify request/response on-the-fly
- Custom response injection

## Browser Configuration

Configure your browser to use the proxy:

**Manual Configuration:**
- Proxy: `127.0.0.1`
- Port: `8081`
- Protocol: HTTP/HTTPS

**System Proxy (macOS):**
```bash
networksetup -setwebproxy Wi-Fi 127.0.0.1 8081
networksetup -setsecurewebproxy Wi-Fi 127.0.0.1 8081
```

**Certificate Installation:**
1. Visit `http://mitm.it` through the proxy
2. Download and install the certificate for your platform
3. Trust the certificate in your system

## Development

### Adding New Routes

Create a new file in `app/api/routes/`:
```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/custom", tags=["custom"])

@router.get("/endpoint")
async def custom_endpoint():
    return {"ok": True, "data": {"message": "Hello"}}
```

Register in `app/api/server.py`:
```python
from app.api.routes import custom
app.include_router(custom.router)
```

### Database Schema

Located in `app/state/repository.py`. Key tables:
- `flows` - HTTP request/response pairs
- `decisions` - User interception decisions
- `config` - Application configuration

## Troubleshooting

**Proxy not starting:**
- Check if port 8081 is available
- Review logs for binding errors

**Certificate errors:**
- Reinstall mitmproxy certificate from `http://mitm.it`
- Ensure certificate is trusted in system keychain

**WebSocket disconnects:**
- Check firewall settings
- Verify `UI_HOST` and `UI_PORT` configuration

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.
