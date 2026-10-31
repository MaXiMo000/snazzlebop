"""Snazzlebop Plus and ads: only Paddle's signed webhooks turn Plus on or pay its perks (unsigned, stale,
forged, resent or someone else's events change nothing), the month's perks pay once, ads stay off only for
Plus members (paid, or a confirmed address on the friends list), and the page only loads third-party code when it's configured."""

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
        self.assertFalse(B.is_plus(None, now))  # a brand-new account: no free period to game
        self.assertFalse(B.is_plus(now - timedelta(days=1), now))  # Plus has run out
        self.assertTrue(B.is_plus(now + timedelta(days=3), now))
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


def test_friends_get_plus_only_by_a_confirmed_address(tmp_path):
    s = settings(tmp_path, rate_auth_burst=1000, plus_friends=("pal@example.com",))
    with TestClient(create_app(s)) as c:
        db = c.app.state.db
        signup(c)
        user = c.portal.call(db.user_by_name, "Ana_99")
        assert c.get("/api/me").json()["user"]["plus"] is False

        # Typing a friend's address on your own account proves nothing until it's confirmed.
        c.portal.call(db.set_email, user.id, "PAL@example.com")
        me = c.get("/api/me").json()["user"]
        assert me["plus"] is False and me["ads"] is True
        assert c.get("/api/me/plus").json()["active"] is False

        assert c.portal.call(db.confirm_email, user.id, "pal@example.com")
        me = c.get("/api/me").json()["user"]
        assert me["plus"] is True and me["ads"] is False and me["plus_until"] is None
        mine = c.get("/api/me/plus").json()
        assert mine["active"] is True and mine["gift"] is True and mine["can_manage"] is False
        assert c.portal.call(db.owns_item, user.id, "emote_spooky")  # every emote pack, as a member

        # A new address (unconfirmed) ends it; so does an address that isn't on the list.
        c.portal.call(db.set_email, user.id, "someone@example.com")
        assert c.get("/api/me").json()["user"]["plus"] is False
        assert c.portal.call(db.confirm_email, user.id, "someone@example.com")
        assert c.get("/api/me").json()["user"]["plus"] is False


def test_the_friends_list_reads_only_addresses():
    from app.config import _emails

    raw = " Pal@Example.com, bo@x.io\nnot-an-email  ,@x.com, cy@site "
    assert _emails(raw) == ("pal@example.com", "bo@x.io")
    assert _emails(None) == ()
    shown = repr(Settings(secret_key="k" * 40, plus_friends=("pal@example.com",)))
    assert "pal@example.com" not in shown  # personal data never lands in logs


def test_ads_txt_names_only_the_configured_publisher(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        r = c.get("/ads.txt")
        assert r.status_code == 200 and r.text == ""  # ads off: nothing to declare
    s = settings(tmp_path, adsense_client="ca-pub-1234567890123456")  # before approval: no slot yet
    with TestClient(create_app(s)) as c:
        r = c.get("/ads.txt")
        assert r.text == "google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0\n"
        assert r.headers["content-type"].startswith("text/plain")


# -- the app stores through RevenueCat: one Plus for the website and the apps ---------------------------
RC_AUTH = "Bearer rc-test-webhook-secret"


@pytest.fixture()
def stores(tmp_path):
    s = settings(
        tmp_path,
        rate_auth_burst=1000,
        paddle_client_token="test_abc",
        paddle_webhook_secret=SECRET,
        paddle_plus_price=PRICE,
        revenuecat_webhook_auth=RC_AUTH,
    )
    with TestClient(create_app(s)) as c:
        yield c


def rc(
    client, kind, app_user, event_id, days=30, store="PLAY_STORE", tx="t1", auth=RC_AUTH, entitlement="plus"
):
    now = datetime.now(UTC)
    event = {
        "id": event_id,
        "type": kind,
        "app_user_id": app_user,
        "aliases": [app_user],
        "store": store,
        "entitlement_ids": [entitlement],
        "original_transaction_id": "orig1",
        "transaction_id": tx,
        "expiration_at_ms": int((now + timedelta(days=days)).timestamp() * 1000),
        "event_timestamp_ms": int(now.timestamp() * 1000),
    }
    return client.post("/api/billing/revenuecat", json={"event": event}, headers={"Authorization": auth})


def test_store_purchases_need_the_secret_and_a_signed_account(stores):
    signup(stores)
    me = stores.get("/api/billing/app-user").json()["app_user_id"]
    assert rc(stores, "INITIAL_PURCHASE", me, "e0", auth="Bearer wrong").status_code == 401
    assert stores.post("/api/billing/revenuecat", json={"event": {}}).status_code == 401  # no header
    forged = me.split(".")[0] + ".00000000000000000000000000000000"
    assert rc(stores, "INITIAL_PURCHASE", forged, "e1").status_code == 200
    assert stores.get("/api/me").json()["user"]["plus"] is False  # credited nobody
    assert rc(stores, "INITIAL_PURCHASE", me, "e2", entitlement="other").status_code == 200
    assert stores.get("/api/me").json()["user"]["plus"] is False  # not the Plus entitlement
    assert rc(stores, "INITIAL_PURCHASE", me, "e3", store="PADDLE").status_code == 200
    assert stores.get("/api/me").json()["user"]["plus"] is False  # Paddle comes straight from Paddle
    coins = stores.get("/api/me").json()["user"]["coins"]
    assert rc(stores, "INITIAL_PURCHASE", me, "e4").status_code == 200
    me_now = stores.get("/api/me").json()["user"]
    assert me_now["plus"] is True and me_now["ads"] is False and me_now["coins"] == coins + 300
    mine = stores.get("/api/me/plus").json()
    assert mine["source"] == "play_store" and mine["can_manage"] is False
    rc(stores, "INITIAL_PURCHASE", me, "e5")  # the same payment again (a resend): perks once
    assert stores.get("/api/me").json()["user"]["coins"] == coins + 300


def test_a_store_expiry_never_cuts_short_a_paid_month_on_the_web(stores):
    signup(stores)
    me = stores.get("/api/billing/app-user").json()["app_user_id"]
    ref = stores.post("/api/billing/checkout").json()["custom_data"]
    send(
        stores,
        event("subscription.activated", subscription(ref, ends=datetime.now(UTC) + timedelta(days=20))),
    )
    rc(stores, "INITIAL_PURCHASE", me, "s1", days=3)
    rc(stores, "EXPIRATION", me, "s2", days=-1)  # the store one ran out
    until = stores.get("/api/me").json()["user"]["plus_until"]
    assert until and datetime.fromisoformat(until) > datetime.now(UTC) + timedelta(days=15)  # web month kept
    assert stores.get("/api/me").json()["user"]["plus"] is True


def test_app_user_ids_round_trip_and_reject_tampering():
    s = Settings(secret_key="k" * 40)
    good = B.app_user_id(s, 42)
    assert B.account_of_app_user(s, good) == 42
    assert B.account_of_app_user(s, good.replace("snz42", "snz43")) is None
    assert B.account_of_app_user(Settings(secret_key="z" * 40), good) is None
    for bad in (None, 42, "", "snz", "snzx.y", "42.abc", "$RCAnonymousID:abc"):
        assert B.account_of_app_user(s, bad) is None
    assert B.store_status("RENEWAL") == "active" and B.store_status("EXPIRATION") == "expired"
    assert B.store_status("TRANSFER") is None


def test_a_full_size_paddle_event_gets_through_and_a_huge_body_does_not(shop):
    """Real subscription events carry whole price and product objects (well over the 4 KB form cap)."""
    signup(shop)
    ref = shop.post("/api/billing/checkout").json()["custom_data"]
    sub = subscription(ref)
    sub["items"][0]["price"].update(
        {"description": "Plus monthly " * 200, "product": {"name": "Plus", "description": "x" * 7000}}
    )
    raw = json.dumps(event("subscription.activated", sub, event_id="evt_big")).encode()
    assert 8_000 < len(raw) < 64 * 1024
    r = shop.post(
        "/api/billing/paddle",
        content=raw,
        headers={"Paddle-Signature": sign(raw), "content-type": "application/json"},
    )
    assert r.status_code == 200, r.text
    assert shop.get("/api/me").json()["user"]["plus"] is True
    huge = b'{"x":"' + b"y" * 100_000 + b'"}'
    r = shop.post(
        "/api/billing/paddle",
        content=huge,
        headers={"Paddle-Signature": sign(huge), "content-type": "application/json"},
    )
    assert r.status_code == 413
    form = b'{"username":"' + b"z" * 6000 + b'"}'
    assert (
        shop.post("/api/auth/login", content=form, headers={"content-type": "application/json"}).status_code
        == 413
    )


def test_mixed_up_paddle_ids_stop_the_deploy_with_a_clear_reason():
    from app.config import load_settings

    base = {"SECRET_KEY": "k" * 40, "ALLOWED_HOSTS": "x.test", "PADDLE_ENV": "production"}
    with pytest.raises(ValueError, match="price id"):
        load_settings({**base, "PADDLE_PLUS_PRICE": "pro_01m67a6rrqfm87rjchqakd72bt"})
    with pytest.raises(ValueError, match="live_"):
        load_settings({**base, "PADDLE_CLIENT_TOKEN": "test_abc"})
    with pytest.raises(ValueError, match="test_"):
        load_settings({**base, "PADDLE_ENV": "sandbox", "PADDLE_CLIENT_TOKEN": "live_abc"})
    ok = load_settings(
        {**base, "PADDLE_CLIENT_TOKEN": "live_abc", "PADDLE_PLUS_PRICE": "pri_01m6742j71p0w02c9yvc25gep0"}
    )
    assert ok.paddle_plus_price.startswith("pri_") and ok.paddle_client_token == "live_abc"


COIN_PRICES = {500: "pri_01coins500x", 1500: "pri_01coins1500", 4000: "pri_01coins4000"}


@pytest.fixture()
def coinshop(tmp_path):
    s = settings(
        tmp_path,
        rate_auth_burst=1000,
        paddle_client_token="test_abc",
        paddle_webhook_secret=SECRET,
        paddle_plus_price=PRICE,
        paddle_coin_packs=tuple(COIN_PRICES.items()),
    )
    with TestClient(create_app(s)) as c:
        yield c


def coin_payment(ref, price, txn="txn_01coins1", qty=1):
    return {"id": txn, "custom_data": ref, "items": [{"price": {"id": price}, "quantity": qty}]}


def refund(txn, status="approved", action="refund"):
    return {"id": "adj_01refund1", "action": action, "status": status, "transaction_id": txn}


def test_coin_packs_pay_once_only_to_the_signed_account_and_refunds_take_them_back(coinshop):
    signup(coinshop)
    packs = coinshop.get("/api/billing/config").json()["coin_packs"]
    assert {p["coins"]: p["price"] for p in packs} == COIN_PRICES
    assert coinshop.post("/api/billing/coins", json={"coins": 999}).status_code == 404  # no such pack
    mine = coinshop.post("/api/billing/coins", json={"coins": 1500}).json()
    assert mine["price"] == COIN_PRICES[1500]
    ref = mine["custom_data"]
    coins = lambda: coinshop.get("/api/me").json()["user"]["coins"]  # noqa: E731
    start = coins()
    # unsigned, someone else's account, an unknown price or the Plus price: nothing
    raw = json.dumps(event("transaction.completed", coin_payment(ref, COIN_PRICES[1500]))).encode()
    assert (
        coinshop.post(
            "/api/billing/paddle", content=raw, headers={"Paddle-Signature": "ts=1;h1=0"}
        ).status_code
        == 401
    )
    send(
        coinshop,
        event(
            "transaction.completed", coin_payment({**ref, "account": "999"}, COIN_PRICES[1500], "t2"), "e2"
        ),
    )
    send(coinshop, event("transaction.completed", coin_payment(ref, "pri_01somethingelse", "t3"), "e3"))
    send(coinshop, event("transaction.completed", coin_payment(None, COIN_PRICES[1500], "t4"), "e4"))
    assert coins() == start
    # paid: credited once, however often Paddle says so
    pay = coin_payment(ref, COIN_PRICES[1500])
    for eid in ("e5", "e5", "e6"):
        send(coinshop, event("transaction.completed", pay, eid))
    assert coins() == start + 1500
    # a refund that isn't approved yet changes nothing; an approved one takes the coins back, once
    send(coinshop, event("adjustment.created", refund("txn_01coins1", "pending_approval"), "e7"))
    assert coins() == start + 1500
    send(coinshop, event("adjustment.updated", refund("txn_01coins1"), "e8"))
    send(coinshop, event("adjustment.updated", refund("txn_01coins1"), "e9"))
    assert coins() == start
    # spent coins aren't chased below zero
    send(coinshop, event("transaction.completed", coin_payment(ref, COIN_PRICES[500], "txn_01coins2"), "e10"))
    set_coins(coinshop, 100)
    send(coinshop, event("adjustment.updated", refund("txn_01coins2", action="chargeback"), "e11"))
    assert coins() == 0
    history = coinshop.get("/api/me/coins").json()["entries"]
    assert {"bought", "refund"} <= {e["reason"] for e in history}


def set_coins(client, n):
    from sqlalchemy import update

    from app.db import User

    db = client.app.state.db

    async def go():
        async with db.sessions() as session:
            await session.execute(update(User).values(coins=n))
            await session.commit()

    client.portal.call(go)


def test_coin_packs_stay_off_without_payments_and_bad_ids_stop_the_deploy(tmp_path):
    from app.config import load_settings

    s = settings(tmp_path, rate_auth_burst=1000, paddle_coin_packs=tuple(COIN_PRICES.items()))
    with TestClient(create_app(s)) as c:
        assert c.get("/api/billing/config").json()["coin_packs"] == []
        signup(c)
        assert c.post("/api/billing/coins", json={"coins": 500}).status_code == 404
    base = {"SECRET_KEY": "k" * 40, "ALLOWED_HOSTS": "x.test"}
    with pytest.raises(ValueError, match="PADDLE_COINS_500"):
        load_settings({**base, "PADDLE_COINS_500": "pro_01m67a6rrqfm87rjchqakd72bt"})
    ok = load_settings({**base, "PADDLE_COINS_500": "pri_01m67wqw63s7wcvrbvvhdac4p8"})
    assert ok.paddle_coin_packs == ((500, "pri_01m67wqw63s7wcvrbvvhdac4p8"),)
