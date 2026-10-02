"""Security primitive tests. Pure Python: `python -m unittest` works with no dependencies."""

from __future__ import annotations

import json
import unittest

from app.config import Settings, load_settings, normalize_database_url
from app.security import (
    BodyLimit,
    HostGuard,
    HttpRateLimit,
    RateLimiter,
    SecurityHeaders,
    client_ip,
    sign_token,
    verify_token,
)

SECRET = "x" * 40


class TokenTests(unittest.TestCase):
    def test_round_trip(self):
        t = sign_token(SECRET, "pid1", "ABCDE", 60, now=1000)
        self.assertEqual(verify_token(SECRET, t, now=1010), ("pid1", "ABCDE"))

    def test_expired(self):
        t = sign_token(SECRET, "pid1", "ABCDE", 60, now=1000)
        self.assertIsNone(verify_token(SECRET, t, now=1061))

    def test_wrong_secret_and_tamper(self):
        t = sign_token(SECRET, "pid1", "ABCDE", 60, now=1000)
        self.assertIsNone(verify_token("y" * 40, t, now=1010))
        payload, sig = t.split(".")
        forged = sign_token(SECRET, "other", "ABCDE", 60, now=1000).split(".")[0] + "." + sig
        self.assertIsNone(verify_token(SECRET, forged, now=1010))

    def test_garbage_never_raises(self):
        for bad in ("", ".", "a.b", "a" * 1000, "....", "%%%.%%%", None, 123, "e30.e30"):
            self.assertIsNone(verify_token(SECRET, bad))  # type: ignore[arg-type]


class RateLimiterTests(unittest.TestCase):
    def test_burst_then_refill(self):
        now = [0.0]
        rl = RateLimiter(rate_per_sec=1, burst=3, clock=lambda: now[0])
        self.assertTrue(all(rl.allow("a") for _ in range(3)))
        self.assertFalse(rl.allow("a"))
        self.assertTrue(rl.allow("b"))  # separate key
        now[0] += 2
        self.assertTrue(rl.allow("a"))
        self.assertTrue(rl.allow("a"))
        self.assertFalse(rl.allow("a"))

    def test_penalty_blocks_longer(self):
        now = [0.0]
        rl = RateLimiter(rate_per_sec=1, burst=5, clock=lambda: now[0])
        rl.penalize("a", 9)
        now[0] += 3
        self.assertFalse(rl.allow("a"))
        now[0] += 10
        self.assertTrue(rl.allow("a"))

    def test_memory_is_bounded(self):
        rl = RateLimiter(1, 1, max_keys=100)
        for i in range(10_000):
            rl.allow(f"ip{i}")
        self.assertLessEqual(len(rl._state), 100)


class ClientIpTests(unittest.TestCase):
    def scope(self, xff=None, peer="10.0.0.1"):
        headers = [(b"x-forwarded-for", xff.encode())] if xff else []
        return {"client": (peer, 1234), "headers": headers}

    def test_no_trusted_proxy_ignores_header(self):
        self.assertEqual(client_ip(self.scope("1.2.3.4"), 0), "10.0.0.1")

    def test_one_hop_uses_rightmost(self):
        # client forges "6.6.6.6"; the trusted proxy appended the real address
        self.assertEqual(client_ip(self.scope("6.6.6.6, 203.0.113.9"), 1), "203.0.113.9")

    def test_two_hops(self):
        self.assertEqual(client_ip(self.scope("6.6.6.6, 203.0.113.9, 172.16.0.2"), 2), "203.0.113.9")

    def test_too_few_entries_falls_back_to_peer(self):
        self.assertEqual(client_ip(self.scope("203.0.113.9"), 2), "10.0.0.1")

    def test_garbage_entry_falls_back(self):
        self.assertEqual(client_ip(self.scope("<script>"), 1), "10.0.0.1")


async def run_asgi(app, scope, body=b"", headers=None):
    sent = []
    queue = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive():
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
        "client": ("1.1.1.1", 1),
        **scope,
    }
    await app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    return (
        start["status"],
        dict(start["headers"]),
        b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body"),
    )


async def ok_app(scope, receive, send):
    await receive()
    await send({"type": "http.response.start", "status": 200, "headers": [(b"server", b"uvicorn")]})
    await send({"type": "http.response.body", "body": b"ok"})


class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_host_guard(self):
        app = HostGuard(ok_app, ("example.com", "*.onrender.com"))
        s, _, _ = await run_asgi(app, {}, headers=[(b"host", b"example.com")])
        self.assertEqual(s, 200)
        s, _, _ = await run_asgi(app, {}, headers=[(b"host", b"app.onrender.com:443")])
        self.assertEqual(s, 200)
        for bad in (b"evil.com", b"example.com.evil.com", b""):
            s, _, _ = await run_asgi(app, {}, headers=[(b"host", bad)])
            self.assertEqual(s, 400)
        s, _, _ = await run_asgi(app, {}, headers=[])
        self.assertEqual(s, 400)
        # health checks work with any host
        s, _, _ = await run_asgi(app, {"path": "/healthz"}, headers=[(b"host", b"10.1.2.3:10000")])
        self.assertEqual(s, 200)

    async def test_security_headers(self):
        app = SecurityHeaders(ok_app, ("example.com",), production=True)
        s, h, _ = await run_asgi(app, {"path": "/api/x"})
        csp = h[b"content-security-policy"].decode()
        self.assertIn("default-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("wss://example.com", csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertNotIn("unsafe-eval", csp)
        self.assertIn(b"strict-transport-security", h)
        self.assertEqual(h[b"x-content-type-options"], b"nosniff")
        self.assertEqual(h[b"cache-control"], b"no-store")
        self.assertNotIn(b"server", h)

    async def test_no_hsts_in_dev(self):
        app = SecurityHeaders(ok_app, ("localhost",), production=False)
        _, h, _ = await run_asgi(app, {})
        self.assertNotIn(b"strict-transport-security", h)

    async def test_body_limit(self):
        app = BodyLimit(ok_app, 10)
        s, _, _ = await run_asgi(app, {"method": "POST"}, body=b"x" * 5, headers=[(b"content-length", b"5")])
        self.assertEqual(s, 200)
        s, _, _ = await run_asgi(
            app, {"method": "POST"}, body=b"x" * 50, headers=[(b"content-length", b"50")]
        )
        self.assertEqual(s, 413)
        s, _, _ = await run_asgi(app, {"method": "POST"}, headers=[(b"content-length", b"abc")])
        self.assertEqual(s, 400)

    async def test_http_rate_limit_tiers(self):
        limiters = {
            "default": RateLimiter(0, 100),
            "create": RateLimiter(0, 2),
            "join": RateLimiter(0, 3),
        }
        app = HttpRateLimit(ok_app, limiters, trusted_hops=0)
        codes = []
        for _ in range(4):
            s, _, _ = await run_asgi(app, {"method": "POST", "path": "/api/rooms"})
            codes.append(s)
        self.assertEqual(codes, [200, 200, 429, 429])
        s, h, body = await run_asgi(app, {"method": "GET", "path": "/api/games"})
        self.assertEqual(s, 200)  # other routes unaffected
        s, _, _ = await run_asgi(app, {"method": "POST", "path": "/api/rooms/ABCDE/join"})
        self.assertEqual(s, 200)
        s, h, body = await run_asgi(app, {"method": "POST", "path": "/api/rooms"})
        self.assertEqual(s, 429)
        self.assertEqual(json.loads(body)["error"]["code"], "rate_limited")
        self.assertIn(b"retry-after", h)

    async def test_health_check_not_rate_limited(self):
        limiters = {k: RateLimiter(0, 0) for k in ("default", "create", "join")}
        app = HttpRateLimit(ok_app, limiters, trusted_hops=0)
        for _ in range(5):
            s, _, _ = await run_asgi(app, {"path": "/healthz"})
            self.assertEqual(s, 200)


class ConfigTests(unittest.TestCase):
    def test_production_requires_strong_secret_and_hosts(self):
        with self.assertRaises(RuntimeError):
            load_settings({"ENV": "production", "ALLOWED_HOSTS": "a.com", "SECRET_KEY": "short"})
        with self.assertRaises(RuntimeError):
            load_settings({"ENV": "production", "SECRET_KEY": "k" * 40})
        s = load_settings({"ENV": "production", "SECRET_KEY": "k" * 40, "ALLOWED_HOSTS": "a.com"})
        self.assertTrue(s.is_production)
        self.assertNotIn("localhost", s.allowed_hosts)

    def test_render_defaults(self):
        s = load_settings(
            {"RENDER": "true", "SECRET_KEY": "k" * 40, "RENDER_EXTERNAL_HOSTNAME": "snazzlebop.onrender.com"}
        )
        self.assertTrue(s.is_production)
        self.assertEqual(s.allowed_hosts, ("snazzlebop.onrender.com",))
        self.assertEqual(s.allowed_origins, ("https://snazzlebop.onrender.com",))

    def test_dev_generates_secret(self):
        a, b = load_settings({}), load_settings({})
        self.assertNotEqual(a.secret_key, b.secret_key)
        self.assertGreaterEqual(len(a.secret_key), 32)

    def test_database_url_normalisation(self):
        self.assertEqual(normalize_database_url("postgres://u:p@h/db"), "postgresql+asyncpg://u:p@h/db")
        self.assertEqual(
            normalize_database_url("postgresql://u:p@h/db?sslmode=require"), "postgresql+asyncpg://u:p@h/db"
        )
        self.assertEqual(normalize_database_url("sqlite+aiosqlite:///x.db"), "sqlite+aiosqlite:///x.db")

    def test_settings_defaults_are_sane(self):
        s = Settings()
        self.assertLessEqual(s.max_players_per_room, 8)
        self.assertLessEqual(s.ws_max_message_bytes, 4096)


if __name__ == "__main__":
    unittest.main()


class LoggingTests(unittest.TestCase):
    def test_uvicorn_socket_lines_with_room_codes_are_dropped(self):
        import logging

        from app.logging_setup import DropSocketPaths

        f = DropSocketPaths()

        def rec(msg, *args):
            return logging.LogRecord("uvicorn.error", logging.INFO, "", 0, msg, args, None)

        self.assertFalse(f.filter(rec('%s - "WebSocket %s" [accepted]', "1.2.3.4:5", "/ws/ABCDE")))
        self.assertTrue(f.filter(rec("Application startup complete.")))
