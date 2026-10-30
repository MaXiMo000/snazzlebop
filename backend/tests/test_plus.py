"""Snazzlebop Plus and ads: only Paddle's signed webhooks turn Plus on or pay its perks (unsigned, stale,
forged, resent or someone else's events change nothing), the month's perks pay once, ads stay off for
new accounts and Plus members, and the page only loads third-party code when it's configured."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import unittest
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import billing as B
from app.config import Settings
from app.main import create_app
from tests.test_accounts import signup
from tests.test_api import settings

SECRET = "pdl_ntfset_test_secret"
PRICE = "pri_01plusmonthly"


def sign(body: bytes, secret: str = SECRET, ts: int | None = None) -> str:
    ts = int(time.time()) if ts is None else ts
    h1 = hmac.new(secret.encode(), f"{ts}:".encode() + body, hashlib.sha256).hexdigest()
    return f"ts={ts};h1={h1}"


class RuleTests(unittest.TestCase):
    def test_signatures(self):
        body = b'{"event_type":"x"}'
        self.assertTrue(B.verify(SECRET, sign(body), body))
        self.assertFalse(B.verify(SECRET, sign(body), body + b" "))  # the raw body, untouched
        self.assertFalse(B.verify(SECRET, sign(body, "another"), body))
        self.assertFalse(
            B.verify(SECRET, sign(body, ts=int(time.time()) - B.SIGNATURE_AGE - 5), body)
        )  # stale
        rotating = sign(body, "old") + ";h1=" + sign(body).split("h1=")[1]
        self.assertTrue(B.verify(SECRET, rotating, body))  # two secrets while one is rotated
        self.assertFalse(B.verify("", sign(body), body))
        self.assertFalse(B.verify(SECRET, "garbage", body))

    def test_the_account_reference_cant_be_forged(self):
        s = Settings(secret_key="k" * 40)
        ref = B.account_ref(s, 7)
        self.assertEqual(B.account_of(s, ref), 7)
        self.assertIsNone(B.account_of(s, {**ref, "account": "8"}))
        self.assertIsNone(B.account_of(Settings(secret_key="z" * 40), ref))
        self.assertIsNone(B.account_of(s, "7"))

    def test_ads_and_plus(self):
        now = datetime.now(UTC)
        self.assertTrue(B.shows_ads(None, now))  # a brand-new account: no free period to game
        self.assertTrue(B.shows_ads(now - timedelta(days=1), now))  # Plus has run out
        self.assertFalse(B.shows_ads(now + timedelta(days=3), now))  # Plus
        end = now + timedelta(days=20)
        self.assertEqual(B.plus_until("active", end, now), end + B.GRACE)
        self.assertEqual(B.plus_until("canceled", end, now), end)  # paid time is kept
        self.assertEqual(B.plus_until("paused", end, now), now)
        self.assertIsNone(B.plus_until("active", None, now))


def test_the_page_stays_same_origin_unless_payments_or_ads_are_set_up(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        h = c.get("/").headers
        assert h["cross-origin-embedder-policy"] == "require-corp"
        assert (
            "frame-src 'none'" in h["content-security-policy"]
            and "paddle" not in h["content-security-policy"]
        )
        assert c.get("/api/billing/config").json()["payments"] is False
    on = settings(
        tmp_path,
        paddle_client_token="test_abc",
        paddle_webhook_secret=SECRET,
        paddle_plus_price=PRICE,
        adsense_client="ca-pub-1234567890123456",
        adsense_slot="1234567890",
    )
    with TestClient(create_app(on)) as c:
        h = c.get("/").headers
        assert "cross-origin-embedder-policy" not in h
        csp = h["content-security-policy"]
        assert "script-src 'self' https://cdn.paddle.com" in csp and "googlesyndication" in csp
        body = c.get("/api/billing/config").json()
        assert (
            body["payments"] and body["plus_price"] == PRICE and body["ads"]["client"].startswith("ca-pub-")
        )


@pytest.fixture()
def shop(tmp_path):
    s = settings(
        tmp_path,
        rate_auth_burst=1000,
        paddle_client_token="test_abc",
        paddle_webhook_secret=SECRET,
        paddle_plus_price=PRICE,
        paddle_api_key="",
    )
    with TestClient(create_app(s)) as c:
        yield c


def event(kind, data, event_id="evt_1", occurred=None):
    return {
        "event_id": event_id,
        "event_type": kind,
        "occurred_at": occurred or datetime.now(UTC).isoformat(),
        "data": data,
    }


def send(client, payload, secret=SECRET):
    raw = json.dumps(payload).encode()
    return client.post(
        "/api/billing/paddle",
        content=raw,
        headers={"Paddle-Signature": sign(raw, secret), "content-type": "application/json"},
    )


def subscription(ref, status="active", ends=None, price=PRICE, sub="sub_01abc"):
    ends = ends or (datetime.now(UTC) + timedelta(days=30))
    return {
        "id": sub,
        "status": status,
        "customer_id": "ctm_01customer0001",
        "custom_data": ref,
        "current_billing_period": {"starts_at": datetime.now(UTC).isoformat(), "ends_at": ends.isoformat()},
        "items": [{"price": {"id": price}}],
    }


def test_only_signed_events_for_the_plus_price_turn_plus_on(shop):
    signup(shop)
    assert shop.get("/api/me").json()["user"]["ads"] is True  # a new account sees ads until it has Plus
    ref = shop.post("/api/billing/checkout").json()["custom_data"]
    raw = json.dumps(event("subscription.activated", subscription(ref))).encode()
    assert (
        shop.post("/api/billing/paddle", content=raw, headers={"Paddle-Signature": "ts=1;h1=00"}).status_code
        == 401
    )
    assert send(shop, event("subscription.activated", subscription(ref)), secret="wrong").status_code == 401
    assert shop.get("/api/me").json()["user"]["plus_until"] is None
    assert (
        send(shop, event("subscription.activated", subscription(ref, price="pri_other"), "evt_0")).status_code
        == 200
    )
    assert shop.get("/api/me").json()["user"]["plus_until"] is None  # not the Plus price
    forged = {**ref, "account": "999"}
    send(shop, event("subscription.activated", subscription(forged, sub="sub_01forged"), "evt_f"))
    assert shop.get("/api/me").json()["user"]["plus_until"] is None
    assert send(shop, event("subscription.activated", subscription(ref))).status_code == 200
    me = shop.get("/api/me").json()["user"]
    assert me["plus_until"] is not None and me["ads"] is False
    plus = shop.get("/api/me/plus").json()
    assert plus["active"] and plus["status"] == "active"


def test_a_paid_month_pays_its_perks_once(shop):
    signup(shop)
    ref = shop.post("/api/billing/checkout").json()["custom_data"]
    send(shop, event("subscription.activated", subscription(ref)))
    paid = {
        "id": "txn_01month1",
        "subscription_id": "sub_01abc",
        "custom_data": ref,
        "items": [{"price": {"id": PRICE}}],
    }
    before = shop.get("/api/me").json()["user"]["coins"]
    send(shop, event("transaction.completed", paid, "evt_t1"))
    send(shop, event("transaction.completed", paid, "evt_t1"))  # a resend
    send(shop, event("transaction.completed", paid, "evt_t2"))  # another event about the same payment
    user = shop.get("/api/me").json()["user"]
    assert user["coins"] == before + B.PLUS_COINS
    assert all(user["powerups"].get(k) == n for k, n in B.PLUS_ITEMS.items())


def test_late_old_events_and_cancels(shop):
    signup(shop)
    ref = shop.post("/api/billing/checkout").json()["custom_data"]
    end = datetime.now(UTC) + timedelta(days=12)
    send(shop, event("subscription.canceled", subscription(ref, "canceled", end), "evt_c"))
    until = shop.get("/api/me/plus").json()["until"]
    assert until.startswith(end.date().isoformat())  # paid time kept after a cancel
    old = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    send(
        shop,
        event("subscription.activated", subscription(ref, "active", end + timedelta(days=60)), "evt_o", old),
    )
    assert shop.get("/api/me/plus").json()["status"] == "canceled"  # the older event changed nothing


def test_checkout_needs_payments_and_a_signed_in_account(tmp_path):
    with TestClient(create_app(settings(tmp_path, rate_auth_burst=1000))) as c:
        assert c.post("/api/billing/checkout").status_code in (401, 403)
        signup(c)
        assert c.post("/api/billing/checkout").json()["error"]["code"] == "payments_off"
        assert c.post("/api/me/plus/manage").json()["error"]["code"] == "no_subscription"


class PlusInRoomTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_badge_and_every_emote_pack(self):
        from app.db import Database, User
        from tests.test_ranked import room_of

        hub, room, pids, _ = await room_of(2, guests=1)
        hub.set_plus(room, pids[0], True)
        hub.set_plus(room, pids[-1], True)  # a guest: no badge
        rows = {p["id"]: p["plus"] for p in hub.view_for(room, pids[1])["players"]}
        assert rows[pids[0]] and not rows[pids[1]] and not rows[pids[-1]]
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.init()
        uid = (await db.create_user("P1_00", "x", "y")).id
        assert not await db.owns_item(uid, "emote_spooky")
        async with db.sessions() as s:
            (await s.get(User, uid)).plus_until = datetime.now(UTC) + timedelta(days=3)
            await s.commit()
        assert await db.owns_item(uid, "emote_spooky")
        assert not await db.owns_item(uid, "party_confetti")  # only emote packs come with Plus


def test_malformed_signed_events_change_nothing(shop):
    signup(shop)
    ref = shop.post("/api/billing/checkout").json()["custom_data"]
    odd = [
        {**subscription(ref), "id": None},  # no subscription id
        {**subscription(ref), "id": "../../etc"},  # not a Paddle subscription id
        {**subscription(ref), "current_billing_period": ["2026"]},  # a period that isn't an object
    ]
    for i, data in enumerate(odd):
        r = send(shop, event("subscription.activated", data, f"evt_odd{i}"))
        assert r.status_code == 200, r.text
    assert send(shop, {"event_type": "x", "event_id": "evt_y", "data": []}).status_code == 400
    assert shop.get("/api/me").json()["user"]["plus_until"] is None  # without a period end, no Plus
    plus = shop.get("/api/me/plus").json()
    assert plus["until"] is None
