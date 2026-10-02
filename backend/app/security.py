"""Security primitives: signed tokens, rate limiting, client IP, and ASGI middleware.

Everything here is framework-light (raw ASGI) so it can be unit-tested without FastAPI.

Honest scope note: application-level limits stop abuse of *this app* (room spam,
message floods, enumeration, slow clients). They cannot absorb a volumetric
network DDoS; put Cloudflare (or similar) in front of Render for that, and set
TRUSTED_PROXY_HOPS accordingly. See SECURITY.md.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

# ---------------------------------------------------------------------------
# Signed player tokens: "<b64url(payload)>.<b64url(hmac)>", payload = pid|code|exp
# ---------------------------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign_token(secret: str, player_id: str, room_code: str, ttl: float, now: float | None = None) -> str:
    exp = int((time.time() if now is None else now) + ttl)
    payload = f"{player_id}|{room_code}|{exp}".encode()
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(sig)}"


def verify_token(secret: str, token: str, now: float | None = None) -> tuple[str, str] | None:
    """Return (player_id, room_code) for a valid, unexpired token, else None."""
    try:
        if not isinstance(token, str) or len(token) > 256 or token.count(".") != 1:
            return None
        payload_b64, sig_b64 = token.split(".")
        payload = _unb64(payload_b64)
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(sig_b64)):
            return None
        pid, code, exp = payload.decode().split("|")
        if int(exp) < (time.time() if now is None else now):
            return None
        return pid, code
    except Exception:  # malformed input of any kind is just "invalid"
        return None


# ---------------------------------------------------------------------------
# Rate limiting (token bucket, bounded memory)
# ---------------------------------------------------------------------------


class RateLimiter:
    def __init__(
        self,
        rate_per_sec: float,
        burst: float,
        max_keys: int = 50_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.rate = rate_per_sec
        self.burst = burst
        self.max_keys = max_keys
        self.clock = clock
        self._state: OrderedDict[str, tuple[float, float]] = OrderedDict()

    def allow(self, key: str, cost: float = 1.0) -> bool:
        now = self.clock()
        tokens, last = self._state.pop(key, (self.burst, now))
        tokens = min(self.burst, tokens + (now - last) * self.rate)
        allowed = tokens >= cost
        if allowed:
            tokens -= cost
        self._state[key] = (tokens, now)
        while len(self._state) > self.max_keys:  # evict least-recently-seen
            self._state.popitem(last=False)
        return allowed

    def penalize(self, key: str, cost: float) -> None:
        """Charge extra tokens (may go negative) for suspicious behaviour, e.g. code guessing."""
        now = self.clock()
        tokens, last = self._state.pop(key, (self.burst, now))
        tokens = min(self.burst, tokens + (now - last) * self.rate) - cost
        self._state[key] = (max(tokens, -self.burst * 4), now)


# ---------------------------------------------------------------------------
# Client IP behind trusted proxies
# ---------------------------------------------------------------------------

_IP_RE = re.compile(r"^[0-9a-fA-F:.]{2,45}$")


def client_ip(scope: dict[str, Any], trusted_hops: int) -> str:
    """Resolve the client IP without trusting forgeable header entries.

    Each trusted proxy appends the address it saw to X-Forwarded-For, so with N
    trusted proxies the real client is the Nth entry from the right. Anything the
    client put further left is ignored.
    """
    peer = (scope.get("client") or ("unknown", 0))[0]
    if trusted_hops <= 0:
        return str(peer)
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-for":
            parts = [p.strip() for p in value.decode("latin-1").split(",") if p.strip()]
            if len(parts) >= trusted_hops:
                candidate = parts[-trusted_hops]
                if _IP_RE.match(candidate):
                    return candidate
            break
    return str(peer)


# ---------------------------------------------------------------------------
# ASGI plumbing
# ---------------------------------------------------------------------------

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def header(scope: Scope, name: bytes) -> str | None:
    for k, v in scope.get("headers", []):
        if k == name:
            return v.decode("latin-1")
    return None


async def send_json(
    send: Send, status: int, body: dict[str, Any], extra: Iterable[tuple[bytes, bytes]] = ()
) -> None:
    raw = json.dumps(body).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(raw)).encode()),
                (b"cache-control", b"no-store"),
                *extra,
            ],
        }
    )
    await send({"type": "http.response.body", "body": raw})


def _error(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


class HostGuard:
    """Reject requests whose Host header is not ours (Host-header attacks, DNS rebinding)."""

    def __init__(self, app: ASGIApp, allowed_hosts: tuple[str, ...]) -> None:
        self.app = app
        self.exact = {h.lower() for h in allowed_hosts if not h.startswith("*.")}
        self.suffixes = tuple(h[1:].lower() for h in allowed_hosts if h.startswith("*."))

    def ok(self, host: str | None) -> bool:
        if not host:
            return False
        host = host.lower()
        if host.startswith("["):  # IPv6 literal, e.g. [::1]:8000
            hostname = host.split("]")[0] + "]"
        else:
            hostname = host.rsplit(":", 1)[0] if ":" in host else host
        if hostname in self.exact:
            return True
        return any(hostname.endswith(s) for s in self.suffixes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            # Platform health checks may use an internal Host; /healthz reveals nothing.
            if scope["type"] == "http" and scope.get("path") == "/healthz":
                return await self.app(scope, receive, send)
            if not self.ok(header(scope, b"host")):
                if scope["type"] == "http":
                    return await send_json(send, 400, _error("bad_host", "Invalid host"))
                return await send({"type": "websocket.close", "code": 1008})
        await self.app(scope, receive, send)


class SecurityHeaders:
    def __init__(self, app: ASGIApp, ws_hosts: tuple[str, ...], production: bool) -> None:
        self.app = app
        connect = " ".join(["'self'", *[f"wss://{h}" for h in ws_hosts if h not in ("testserver",)]])
        if not production:
            connect += " ws://localhost:* ws://127.0.0.1:* http://localhost:* http://127.0.0.1:*"
        self.csp = "; ".join(
            [
                "default-src 'none'",
                "script-src 'self'",
                "style-src 'self'",
                "img-src 'self' data:",
                "font-src 'self'",
                f"connect-src {connect}",
                "manifest-src 'self'",
                "base-uri 'none'",
                "form-action 'self'",
                "frame-ancestors 'none'",
                "object-src 'none'",
            ]
        )
        self.production = production

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        is_api = scope.get("path", "").startswith("/api/")

        async def wrapped(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"server"]
                add = {
                    b"content-security-policy": self.csp.encode(),
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                    b"referrer-policy": b"no-referrer",
                    b"permissions-policy": b"camera=(), microphone=(), geolocation=(), payment=(), usb=()",
                    b"cross-origin-opener-policy": b"same-origin",
                    b"cross-origin-resource-policy": b"same-origin",
                    b"cross-origin-embedder-policy": b"require-corp",  # everything is same-origin
                }
                if self.production:
                    add[b"strict-transport-security"] = b"max-age=63072000; includeSubDomains; preload"
                if is_api:
                    add[b"cache-control"] = b"no-store"
                existing = {k.lower() for k, _ in headers}
                headers += [(k, v) for k, v in add.items() if k not in existing]
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, wrapped)


class BodyLimit:
    """Cap request bodies: by Content-Length up front, and by counting streamed bytes."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        declared = header(scope, b"content-length")
        if declared is not None:
            try:
                if int(declared) > self.max:
                    return await send_json(send, 413, _error("too_large", "Request too large"))
            except ValueError:
                return await send_json(send, 400, _error("bad_request", "Bad Content-Length"))
        seen = 0

        async def limited() -> dict[str, Any]:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max:
                    return {"type": "http.disconnect"}
            return message

        await self.app(scope, limited, send)


class HttpRateLimit:
    """Per-IP token buckets, with tighter buckets for room creation and joining."""

    def __init__(self, app: ASGIApp, limiters: dict[str, RateLimiter], trusted_hops: int) -> None:
        self.app = app
        self.limiters = limiters
        self.hops = trusted_hops

    def bucket_for(self, scope: Scope) -> str:
        path, method = scope.get("path", ""), scope.get("method", "GET")
        if method == "POST" and path == "/api/rooms":
            return "create"
        if method == "POST" and path.startswith("/api/rooms/") and path.endswith(("/join", "/tv")):
            return "join"
        return "default"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") == "/healthz":
            return await self.app(scope, receive, send)
        ip = client_ip(scope, self.hops)
        name = self.bucket_for(scope)
        if not self.limiters[name].allow(ip):
            return await send_json(
                send, 429, _error("rate_limited", "Slow down a little"), [(b"retry-after", b"10")]
            )
        # Every request also counts against the global per-IP bucket.
        if name != "default" and not self.limiters["default"].allow(ip):
            return await send_json(
                send, 429, _error("rate_limited", "Slow down a little"), [(b"retry-after", b"10")]
            )
        await self.app(scope, receive, send)
