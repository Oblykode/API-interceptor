# HTTPS Interception Setup

To intercept HTTPS traffic, your browser/device must trust mitmproxy's local CA certificate.

## 1. Start Services

```bash
python main.py all
```

Confirm active ports first:

```bash
python -c "from app.core.config import get_settings as g; s=g(); print('UI=',s.ui_host,s.ui_port,'PROXY=',s.proxy_host,s.proxy_port)"
```

## 2. Configure Browser Proxy

Set browser proxy manually:
- HTTP proxy: `PROXY_HOST`
- HTTP port: `PROXY_PORT`
- HTTPS proxy: same host/port

For current local `.env`, this is typically `127.0.0.1:8080`.

## 3. Install mitmproxy Certificate

1. Open `http://mitm.it` in the proxied browser.
2. Download certificate for your platform.
3. Install certificate as trusted root CA.

### Windows

Install downloaded cert into:
- `Trusted Root Certification Authorities` (Current User or Local Machine)

### Firefox-specific note

Firefox can use its own certificate store. If HTTPS still fails:
- open `about:preferences#privacy`
- certificates section
- import mitmproxy cert there

## 4. Validate

1. Browse to `https://example.com`.
2. Confirm flow appears in interceptor UI.
3. Confirm no TLS warning in browser.

## 5. Troubleshooting

- "Proxy server is refusing connections":
  proxy process is not listening on configured `PROXY_HOST:PROXY_PORT`.
- HTTP works but HTTPS fails:
  certificate not trusted in browser/store.
- No flows in UI:
  verify browser is actually using proxy and check `/health`.
- Too much Firefox background noise:
  `detectportal.firefox.com` is ignored by default via `IGNORED_HOSTS`.

