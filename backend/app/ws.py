"""WebSocket endpoint: origin check, per-IP caps, auth handshake, flood protection."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from .rooms import Hub, Room
from .security import RateLimiter, client_ip, verify_token

log = logging.getLogger("snazzlebop.ws")


class ConnectionCounter:
    def __init__(self) -> None:
        self.total = 0
        self.per_ip: dict[str, int] = defaultdict(int)

    def add(self, ip: str) -> None:
        self.total += 1
        self.per_ip[ip] += 1

    def remove(self, ip: str) -> None:
        self.total = max(0, self.total - 1)
        self.per_ip[ip] -= 1
        if self.per_ip[ip] <= 0:
            self.per_ip.pop(ip, None)


class WSConn:
    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws

    async def send_json(self, data: dict[str, Any]) -> None:
        await self.ws.send_json(data)

    async def close(self, code: int = 1000) -> None:
        await self.ws.close(code=code)


def _origin_ok(ws: WebSocket, allowed: tuple[str, ...], production: bool) -> bool:
    origin = ws.headers.get("origin")
    if origin is None:
        # Browsers always send Origin. Non-browser tools (and tests) may not.
        return not production
    return origin in allowed


async def _authenticate(ws: WebSocket, hub: Hub, room: Room, deadline: float, max_bytes: int) -> str | None:
    try:
        raw = await asyncio.wait_for(ws.receive_text(), deadline)
        if len(raw.encode()) > max_bytes:
            return None
        msg = json.loads(raw)
    except Exception:
        return None
    if not isinstance(msg, dict) or msg.get("t") != "auth":
        return None
    verified = verify_token(hub.settings.secret_key, msg.get("token", ""))
    if verified is None:
        return None
    pid, code = verified
    if code != room.code or pid not in room.players:
        return None
    return pid


async def serve_socket(ws: WebSocket, code: str) -> None:
    state = ws.app.state
    settings = state.settings
    hub: Hub = state.hub
    counter: ConnectionCounter = state.ws_counter
    ip = client_ip(ws.scope, settings.trusted_proxy_hops)

    if not _origin_ok(ws, settings.allowed_origins, settings.is_production):
        await ws.close(code=1008)
        return
    room = hub.get(code)
    if room is None:
        await ws.close(code=1008)
        return
    if counter.total >= settings.max_ws_total or counter.per_ip.get(ip, 0) >= settings.max_ws_per_ip:
        await ws.close(code=1013)
        return

    counter.add(ip)
    conn = WSConn(ws)
    pid: str | None = None
    try:
        await ws.accept()
        pid = await _authenticate(ws, hub, room, settings.ws_auth_timeout, settings.ws_max_message_bytes)
        if pid is None:
            await ws.close(code=1008)
            return
        await hub.connect(room, pid, conn)

        bucket = RateLimiter(settings.ws_msgs_per_second, settings.ws_msg_burst, max_keys=1)
        while True:
            try:
                text = await asyncio.wait_for(ws.receive_text(), settings.ws_idle_timeout)
            except TimeoutError:
                await ws.close(code=1001)
                break
            except Exception:  # disconnect, or a non-text frame
                break
            if len(text.encode()) > settings.ws_max_message_bytes:
                await ws.close(code=1009)
                break
            if not bucket.allow("c"):
                await ws.close(code=1008)
                break
            try:
                msg = json.loads(text)
            except (ValueError, RecursionError):
                await hub.send_error(conn, "bad_message", "Could not read that message")
                continue
            await hub.handle_message(room, pid, conn, msg)
    finally:
        counter.remove(ip)
        if pid is not None:
            await hub.disconnect(room, pid, conn)
