"""Application logging bootstrap."""

from __future__ import annotations

import logging
from typing import Any

_DEFAULT_FORMAT = "%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s"
_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class KeyValueFormatter(logging.Formatter):
    _reserved = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
        "message",
        "asctime",
    }

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras: list[str] = []
        for key, value in record.__dict__.items():
            if key in self._reserved or key.startswith("_"):
                continue
            extras.append(f"{key}={_to_log_token(value)}")
        if extras:
            return f"{base} {' '.join(extras)}"
        return base


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with key/value formatting."""
    normalized = level.upper()
    if normalized not in _LEVELS:
        normalized = "INFO"

    handler = logging.StreamHandler()
    handler.setFormatter(KeyValueFormatter(_DEFAULT_FORMAT))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(normalized)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return namespaced logger."""
    return logging.getLogger(name)


def log_kv(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    """Log with structured extra fields."""
    logger.log(level, message, extra=fields)


def _to_log_token(value: Any) -> str:
    if value is None:
        return "null"
    text = str(value).replace("\n", "\\n")
    if " " in text or "\t" in text:
        return f"\"{text}\""
    return text
