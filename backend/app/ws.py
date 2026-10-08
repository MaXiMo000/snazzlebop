"""WebSocket endpoint: origin check, per-IP caps, auth handshake, flood protection."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from .rooms import Hub, Room
from .security import RateLimiter, client_ip, verify_token

FLOOD = 4008  # WebSocket close: too many messages; reconnecting is allowed

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


async def _close(ws: WebSocket, code: int) -> None:
    # The peer may already be gone (closing an already-closed socket raises); nothing to do then.
    with contextlib.suppress(Exception):
        await ws.close(code=code)


def _origin_ok(ws: WebSocket, allowed: tuple[str, ...], production: bool) -> bool:
    origin = ws.headers.get("origin")
    if origin is None:
        # Browsers always send Origin. Non-browser tools (and tests) may not.
        return not production
    return origin in allowed


async def _authenticate(
    ws: WebSocket, hub: Hub, code: str, room: Room | None, deadline: float, max_bytes: int
) -> tuple[str | None, bool]:
    """Return (player_id or None, suspicious). Suspicious = a token that isn't genuinely for this
    code, i.e. what a code guesser sends. A real token for a room that has since ended is not."""
    try:
        raw = await asyncio.wait_for(ws.receive_text(), deadline)
    except Exception:  # timeout or the client left without saying anything
        return None, False
    try:
        msg = json.loads(raw) if len(raw.encode()) <= max_bytes else None
    except (ValueError, RecursionError):
        msg = None
    token = msg.get("token", "") if isinstance(msg, dict) and msg.get("t") == "auth" else ""
    verified = verify_token(hub.settings.secret_key, token)
    if verified is None or verified[1] != code:
        return None, True
    pid = verified[0]
    if room is None or not hub.is_member(room, pid):
        return None, False
    return pid, False


async def serve_socket(ws: WebSocket, code: str) -> None:
    state = ws.app.state
    settings = state.settings
    hub: Hub = state.hub
    counter: ConnectionCounter = state.ws_counter
    ip = client_ip(ws.scope, settings.trusted_proxy_hops, settings.client_ip_header)

    if not _origin_ok(ws, settings.allowed_origins, settings.is_production):
        await _close(ws, 1008)
        return
    join_bucket: RateLimiter = state.limiters["join"]
    # Handshakes are rate limited like HTTP requests, and an IP that has been guessing codes
    # (join bucket in debt) gets no sockets at all until it cools down.
    if not state.limiters["default"].allow(ip) or not join_bucket.allow(ip, cost=0):
        await _close(ws, 1013)
        return
    # An unknown room is NOT refused here: it fails at auth exactly like a bad token, so the
    # socket can't be used to test which codes exist.
    room = await hub.fetch(code)  # restored from its snapshot if the server restarted
    if counter.total >= settings.max_ws_total or counter.per_ip.get(ip, 0) >= settings.max_ws_per_ip:
        await _close(ws, 1013)
        return

    counter.add(ip)
    conn = WSConn(ws)
    pid: str | None = None
    try:
        await ws.accept()
        pid, suspicious = await _authenticate(
            ws, hub, code, room, settings.ws_auth_timeout, settings.ws_max_message_bytes
        )
        if pid is None or room is None:
            if suspicious:
                join_bucket.penalize(ip, 4)  # same price as a wrong code on HTTP join
            await _close(ws, 1008)
            return
        await hub.connect(room, pid, conn)

        bucket = RateLimiter(settings.ws_msgs_per_second, settings.ws_msg_burst, max_keys=1)
        while True:
            try:
                text = await asyncio.wait_for(ws.receive_text(), settings.ws_idle_timeout)
            except TimeoutError:
                await _close(ws, 1001)
                break
            except Exception:  # disconnect, or a non-text frame
                break
            if len(text.encode()) > settings.ws_max_message_bytes:
                await _close(ws, 1009)
                break
            if not bucket.allow("c"):
                # 4008 "slow down", not 1008: the client may reconnect (the handshake is rate limited
                # too), so a burst of taps never looks like "the room has ended".
                await _close(ws, FLOOD)
                break
            try:
                msg = json.loads(text)
            except (ValueError, RecursionError):
                await hub.send_error(conn, "bad_message", "Could not read that message")
                continue
            await hub.handle_message(room, pid, conn, msg)
    finally:
        counter.remove(ip)
        if pid is not None and room is not None:
            await hub.disconnect(room, pid, conn)
