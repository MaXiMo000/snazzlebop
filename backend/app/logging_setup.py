"""Tiny JSON logger. Never log tokens, player names, room codes or request bodies."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


class DropSocketPaths(logging.Filter):
    """uvicorn logs '"WebSocket /ws/<CODE>" [accepted]' on uvicorn.error, which --no-access-log
    doesn't cover. Those lines carry the room code and client IP, so drop them."""

    def filter(self, record: logging.LogRecord) -> bool:
        return '"WebSocket ' not in record.getMessage()


def setup_logging(production: bool) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO if production else logging.DEBUG)
    # uvicorn's access log would record room codes in URLs; we run it with --no-access-log.
    logging.getLogger("uvicorn.access").disabled = True
    uv_error = logging.getLogger("uvicorn.error")
    if not any(isinstance(f, DropSocketPaths) for f in uv_error.filters):
        uv_error.addFilter(DropSocketPaths())
    logging.getLogger("aiosqlite").setLevel(logging.INFO)  # per-query debug noise
