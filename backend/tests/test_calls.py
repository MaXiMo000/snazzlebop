"""Calls (LiveKit): signed join passes, who may publish, the room name never revealing the code, off
without configuration, rate limits, and the security headers that open only for calls."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import unittest

from app import calls
from app.config import Settings
from app.security import SecurityHeaders

from .test_rooms import FakeConn, HubHarness

LK = {
    "livekit_url": "wss://party.livekit.cloud",
    "livekit_api_key": "APIkey123",
    "livekit_api_secret": "s" * 40,
}


def decode(token: str, secret: str) -> dict:
    head, body, sig = token.split(".")
    want = hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    got = base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
    assert hmac.compare_digest(want, got), "bad signature"
    assert json.loads(base64.urlsafe_b64decode(head + "==="))["alg"] == "HS256"
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))


class TokenTests(unittest.TestCase):
    def test_join_token(self):
        s = Settings(secret_key="k" * 40, **LK)
        claims = decode(calls.join_token(s, "snz-abc", "p1", "Ana", can_publish=True), s.livekit_api_secret)
        self.assertEqual((claims["iss"], claims["sub"], claims["name"]), ("APIkey123", "p1", "Ana"))
        v = claims["video"]
        self.assertEqual(
            (v["room"], v["roomJoin"], v["canPublish"], v["canPublishData"]), ("snz-abc", True, True, False)
        )
        self.assertLessEqual(claims["exp"] - claims["nbf"], calls.TOKEN_TTL + 10)

    def test_room_name_hides_the_code(self):
        s = Settings(secret_key="k" * 40, **LK)
        name = calls.room_name(s, "ABCDE", 123.0)
        self.assertNotIn("ABCDE", name)
        self.assertEqual(name, calls.room_name(s, "ABCDE", 123.0))
        self.assertNotEqual(name, calls.room_name(s, "ABCDE", 124.0))  # a new room with a reused code

    def test_enabled_and_headers(self):
        self.assertFalse(calls.enabled(Settings(secret_key="k" * 40)))
        on = Settings(secret_key="k" * 40, **LK)
        self.assertTrue(calls.enabled(on))
        self.assertIn("wss://party.livekit.cloud", calls.csp_hosts(on))
        off_headers = SecurityHeaders(None, (), True)  # type: ignore[arg-type]
        on_headers = SecurityHeaders(None, (), True, call_hosts=calls.csp_hosts(on))  # type: ignore[arg-type]
        self.assertIn(b"camera=()", off_headers.permissions)
        self.assertIn(b"camera=(self)", on_headers.permissions)
        self.assertNotIn("livekit", off_headers.csp)
        self.assertIn("wss://party.livekit.cloud", on_headers.csp)


class HubCallTests(HubHarness):
    async def test_passes(self):
        hub = self.make_hub(**LK)
        room, host, conns = await self.party(hub, 2)
        # Guests can't: calls are for signed-in accounts.
        await hub.handle_message(room, host, conns[host], {"t": "call"})
        self.assertIn("sign_in", conns[host].errors())
        self.assertFalse(conns[host].last["call"]["allowed"])
        self.assertFalse(any(m["t"] == "call" for m in conns[host].sent))
        hub.link_account(room, host, 7)
        await hub.handle_message(room, host, conns[host], {"t": "call"})
        msg = next(m for m in conns[host].sent if m["t"] == "call")
        claims = decode(msg["token"], LK["livekit_api_secret"])
        self.assertTrue(claims["video"]["canPublish"])
        self.assertEqual(msg["url"], LK["livekit_url"])
        await hub.broadcast(room)
        self.assertTrue(conns[host].last["call"]["available"])
        self.assertTrue(conns[host].last["call"]["allowed"])
        guest = next(p for p in room.players if p != host)
        self.assertFalse(conns[guest].last["call"]["allowed"])
        # Too soon again: refused.
        await hub.handle_message(room, host, conns[host], {"t": "call"})
        self.assertIn("slow_down", conns[host].errors())
        # The TV watches only; the audience may talk.
        _, _tv = hub.issue_tv(room.code)
        vid = next(iter(room.viewers))
        screen = FakeConn()
        await hub.connect(room, vid, screen)
        await hub.handle_message(room, vid, screen, {"t": "call"})
        tv_claims = decode(
            next(m for m in screen.sent if m["t"] == "call")["token"], LK["livekit_api_secret"]
        )
        self.assertFalse(tv_claims["video"]["canPublish"])
        _, fan, _ = hub.join_audience(room.code, "Fan", 8)
        fan_conn = FakeConn()
        await hub.connect(room, fan.id, fan_conn)
        await hub.handle_message(room, fan.id, fan_conn, {"t": "call"})
        fan_claims = decode(
            next(m for m in fan_conn.sent if m["t"] == "call")["token"], LK["livekit_api_secret"]
        )
        self.assertTrue(fan_claims["video"]["canPublish"])
        # Every pass in the room is for the same call; the code itself never appears.
        self.assertEqual(
            {claims["video"]["room"], tv_claims["video"]["room"], fan_claims["video"]["room"]},
            {calls.room_name(hub.settings, room.code, room.created)},
        )
        self.assertNotIn(room.code, claims["video"]["room"])

    async def test_off_without_configuration(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 2)
        self.assertFalse(conns[host].last["call"]["available"])
        await hub.handle_message(room, host, conns[host], {"t": "call"})
        self.assertIn("no_calls", conns[host].errors())
