"""Accounts, coins and power-ups: sign-up/log-in/recovery and their security (cookie flags, same message
for unknown users, lockout, cross-site writes refused, sessions killed on password change), coins for
places with a daily cap, the shop, and power-ups in a live game (one per game, refunded on failure)."""

from __future__ import annotations

import asyncio
import contextlib
import random
import unittest

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app import coins  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.rooms import Hub, HubError  # noqa: E402
from tests.test_api import settings  # noqa: E402
from tests.test_rooms import FAST, Clock, FakeConn  # noqa: E402

PW = "correct horse battery"


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(settings(tmp_path, rate_auth_burst=1000))) as c:
        yield c


def signup(client, name="Ana_99", pw=PW):
    r = client.post("/api/auth/signup", json={"username": name, "password": pw})
    assert r.status_code == 201, r.text
    return r.json()


def test_signup_sets_a_safe_cookie_and_shows_the_recovery_code_once(client):
    r = client.post("/api/auth/signup", json={"username": "Ana_99", "password": PW})
    assert r.status_code == 201
    body = r.json()
    assert body["user"] == {"username": "Ana_99", "coins": 0, "powerups": {}}
    assert len(body["recovery_code"].replace("-", "")) == 20
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "max-age=" in cookie
    assert client.get("/api/me").json()["user"]["username"] == "Ana_99"
    assert "recovery" not in str(client.get("/api/me").json())


def test_bad_usernames_and_passwords(client):
    for name in ("ab", "x" * 21, "has space", "<b>", "ana@x", ""):
        r = client.post("/api/auth/signup", json={"username": name, "password": PW})
        assert r.status_code == 400 and r.json()["error"]["code"] == "bad_username", name
    for pw in ("short", "password123", "Ana_99"):
        r = client.post("/api/auth/signup", json={"username": "Ana_99", "password": pw})
        assert r.json()["error"]["code"] == "weak_password", pw
    r = client.post("/api/auth/signup", json={"username": "Ana_99", "password": "x" * 129})
    assert r.status_code == 422  # too long to even hash
    signup(client)
    r = client.post("/api/auth/signup", json={"username": "ana_99", "password": PW})
    assert r.status_code == 409  # usernames are unique, whatever the capitals


def test_login_logout_and_the_same_answer_for_unknown_users(client):
    signup(client)
    client.post("/api/auth/logout")
    assert client.get("/api/me").json()["user"] is None
    wrong = client.post("/api/auth/login", json={"username": "Ana_99", "password": "nope nope nope"})
    nobody = client.post("/api/auth/login", json={"username": "Nobody_here", "password": "nope nope nope"})
    assert wrong.status_code == nobody.status_code == 401
    assert wrong.json() == nobody.json()
    ok = client.post("/api/auth/login", json={"username": "ana_99", "password": PW})
    assert ok.status_code == 200 and client.get("/api/me").json()["user"]["username"] == "Ana_99"


def test_repeated_wrong_passwords_lock_the_username(client):
    signup(client)
    client.post("/api/auth/logout")
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "Ana_99", "password": "wrong guess 1"})
    r = client.post("/api/auth/login", json={"username": "Ana_99", "password": PW})
    assert r.status_code == 429  # even the right password waits out the lock


def test_cross_site_writes_are_refused(client):
    signup(client)
    evil = {"Origin": "https://evil.example"}
    assert client.post("/api/auth/logout", headers=evil).status_code == 403
    assert client.post("/api/shop/buy", json={"item": "peek"}, headers=evil).status_code == 403
    r = client.post("/api/me/delete", json={"password": PW}, headers=evil)
    assert r.status_code == 403
    assert client.get("/api/me").json()["user"] is not None


def test_recovery_resets_the_password_and_signs_out_everywhere(client, tmp_path):
    code = signup(client)["recovery_code"]
    other = TestClient(client.app)
    assert other.post("/api/auth/login", json={"username": "Ana_99", "password": PW}).status_code == 200
    bad = client.post(
        "/api/auth/recover",
        json={
            "username": "Ana_99",
            "recovery_code": "AAAAA-BBBBB-CCCCC-DDDDD",
            "new_password": "new pass 12345",
        },
    )
    assert bad.status_code == 401
    r = client.post(
        "/api/auth/recover",
        json={"username": "Ana_99", "recovery_code": code.lower(), "new_password": "new pass 12345"},
    )
    assert r.status_code == 200 and r.json()["recovery_code"] != code
    assert other.get("/api/me").json()["user"] is None  # the other browser was signed out
    again = client.post(
        "/api/auth/recover",
        json={"username": "Ana_99", "recovery_code": code, "new_password": "another pass 1"},
    )
    assert again.status_code == 401  # a used code is spent
    client.post("/api/auth/logout")
    assert (
        client.post("/api/auth/login", json={"username": "Ana_99", "password": "new pass 12345"}).status_code
        == 200
    )


def test_change_password_and_delete_account(client):
    signup(client)
    r = client.post("/api/me/password", json={"password": "wrong one here", "new_password": "fresh pass 123"})
    assert r.status_code == 401
    r = client.post("/api/me/password", json={"password": PW, "new_password": "fresh pass 123"})
    assert r.status_code == 200 and client.get("/api/me").json()["user"] is not None
    assert client.post("/api/me/delete", json={"password": PW}).status_code == 401
    assert client.post("/api/me/delete", json={"password": "fresh pass 123"}).status_code == 200
    assert client.get("/api/me").json()["user"] is None
    r = client.post("/api/auth/login", json={"username": "Ana_99", "password": "fresh pass 123"})
    assert r.status_code == 401


def test_coins_for_places_daily_cap_shop_and_leaderboard(client):
    signup(client)
    db = client.app.state.db
    user = client.portal.call(db.user_by_name, "Ana_99")
    rows = [{"user_id": user.id, "game_id": "lonely", "place": 1, "players": 4, "points": 300, "coins": 50}]
    paid = {}
    for _ in range(13):  # 13 x 50 = 650, but the day caps at 600
        paid = client.portal.call(db.record_results, rows, coins.season_of(), coins.DAILY_COIN_CAP)
    assert paid == {user.id: 0}
    assert client.get("/api/me").json()["user"]["coins"] == 600
    r = client.post("/api/shop/buy", json={"item": "double"})
    assert r.status_code == 200 and r.json()["user"] == {
        "username": "Ana_99",
        "coins": 520,
        "powerups": {"double": 1},
    }
    assert client.post("/api/shop/buy", json={"item": "gold bar"}).status_code == 400
    for _ in range(8):
        client.post("/api/shop/buy", json={"item": "double"})
    r = client.post("/api/shop/buy", json={"item": "double"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "not_enough_coins"
    stats = client.get("/api/me/stats").json()
    assert stats["totals"] == {"played": 13, "wins": 13, "coins": 600}
    assert stats["season"]["rank"] == 1
    board = client.get("/api/leaderboard").json()
    assert board["rows"][0]["username"] == "Ana_99" and board["rows"][0]["points"] == 600
    assert client.get("/api/shop").json()["items"][0]["price"] > 0
    client.post("/api/auth/logout")
    assert client.post("/api/shop/buy", json={"item": "peek"}).status_code == 401


def test_rooms_remember_the_account_but_never_show_it(client):
    signup(client)
    r = client.post("/api/rooms", json={"name": "Ana"})
    room = client.app.state.hub.rooms[r.json()["code"]]
    assert list(room.accounts.values()) == [client.portal.call(client.app.state.db.user_by_name, "Ana_99").id]
    view = client.app.state.hub.view_for(room, r.json()["player_id"])
    assert "accounts" not in str(view) and "user_id" not in str(view)


# -- the rules, pure ----------------------------------------------------------------------------------
def test_friends_see_each_others_rooms_only_when_both_added(client):
    signup(client, "Ana_99")
    client.cookies.clear()
    signup(client, "Bo_77")
    bo = dict(client.cookies)
    assert client.post("/api/friends", json={"username": "nobody_1"}).status_code == 404
    assert client.post("/api/friends", json={"username": "bo_77"}).status_code == 400
    assert (
        client.post(
            "/api/friends", json={"username": "ana_99"}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert client.post("/api/friends", json={"username": "ana_99"}).status_code == 200
    assert client.get("/api/friends").json() == {"friends": [], "sent": ["Ana_99"], "asked": []}

    # Ana hosts a room. Bo added her, but she hasn't added him: he sees nothing.
    client.cookies.clear()
    client.post("/api/auth/login", json={"username": "Ana_99", "password": PW})
    code = client.post("/api/rooms", json={"name": "Ana"}).json()["code"]
    hub = client.app.state.hub
    room = hub.get(code)
    room.players[room.host_id].connected = True
    assert client.get("/api/friends").json() == {"friends": [], "sent": [], "asked": ["Bo_77"]}
    client.cookies.clear()
    client.cookies.update(bo)
    assert client.get("/api/friends").json()["friends"] == []

    # She adds him back: now he sees her room, until she locks it.
    client.cookies.clear()
    client.post("/api/auth/login", json={"username": "Ana_99", "password": PW})
    assert client.post("/api/friends", json={"username": "Bo_77"}).status_code == 200
    client.cookies.clear()
    client.cookies.update(bo)
    assert client.get("/api/friends").json()["friends"] == [{"username": "Ana_99", "room": code}]
    room.locked = True
    assert client.get("/api/friends").json()["friends"] == [{"username": "Ana_99", "room": None}]
    assert client.post("/api/friends/remove", json={"username": "Ana_99"}).status_code == 200
    assert client.get("/api/friends").json() == {"friends": [], "sent": [], "asked": ["Ana_99"]}
    client.cookies.clear()
    assert client.get("/api/friends").status_code == 401


def test_places_and_coins():
    assert coins.places({"a": 300, "b": 300, "c": 100, "d": 0}) == {"a": 1, "b": 1, "c": 3, "d": 4}
    assert [coins.coins_for(p, 5) for p in (1, 2, 3, 4, 5)] == [50, 30, 20, 10, 5]
    assert coins.coins_for(1, 1) == 0  # no coins for playing alone
    assert len(coins.season_of()) == 7


# -- power-ups in a live game -------------------------------------------------------------------------
class Wallet:
    def __init__(self, owned):
        self.owned = dict(owned)
        self.paid: list = []

    async def spend(self, uid, item):
        if self.owned.get((uid, item), 0) < 1:
            return False
        self.owned[(uid, item)] -= 1
        return True

    async def refund(self, uid, item):
        self.owned[(uid, item)] = self.owned.get((uid, item), 0) + 1

    async def pay(self, rows):
        self.paid.append(rows)
        return {r["user_id"]: r["coins"] for r in rows}


async def live_game(wallet):
    clock = Clock()
    hub = Hub(
        Settings(secret_key="s" * 40),
        clock=clock,
        rng=random.Random(3),
        timings=FAST,
        intro_seconds=0,
        on_results=wallet.pay,
        spend_powerup=wallet.spend,
        refund_powerup=wallet.refund,
    )
    room, host, _ = hub.create_room("Host", user_id=1)
    conns = {host.id: FakeConn()}
    _, guest, _ = hub.join_room(room.code, "Guest", user_id=2)
    _, anon, _ = hub.join_room(room.code, "Anon")
    for p in (host, guest, anon):
        conns.setdefault(p.id, FakeConn())
        await hub.connect(room, p.id, conns[p.id])
    await hub.handle_message(room, host.id, conns[host.id], {"t": "start", "game": "lonely"})
    return hub, room, host.id, guest.id, anon.id, conns


class PowerUpTests(unittest.IsolatedAsyncioTestCase):
    async def test_power_ups_one_per_game_spent_from_the_wallet_and_coins_paid(self):
        wallet = Wallet({(1, "double"): 1, (1, "steal"): 1, (2, "peek"): 1})
        hub, room, host, guest, anon, conns = await live_game(wallet)
        await hub.handle_message(room, anon, conns[anon], {"t": "boost", "item": "double"})
        assert "signed_out" in conns[anon].errors()
        await hub.handle_message(room, guest, conns[guest], {"t": "boost", "item": "double"})
        assert "no_powerup" in conns[guest].errors()  # doesn't own one
        await hub.handle_message(room, host, conns[host], {"t": "boost", "item": "double"})
        assert wallet.owned[(1, "double")] == 0
        assert conns[host].last["cards"]["you"]["boost"] == "double"
        assert conns[guest].last["cards"]["in_play"] == 1  # how many, never whose
        await hub.handle_message(room, host, conns[host], {"t": "boost", "item": "steal", "target": guest})
        assert "already_used" in conns[host].errors()
        assert wallet.owned[(1, "steal")] == 1  # refused before anything was spent
        # finish the game: the double applies, then coins are paid for the two accounts only
        for _ in range(40):
            if room.phase != "game":
                break
            await hub.handle_message(room, host, conns[host], {"t": "skip", "stage": room.game.stage})
        await asyncio.gather(*list(hub._tasks))
        assert room.phase == "results"
        assert [n["card"] for n in room.card_news] == ["double"]
        assert {r["user_id"] for r in wallet.paid[0]} == {1, 2}
        news = conns[guest].last["cards"]["coins"]
        assert set(news) == {host, guest} and all(v["coins"] > 0 for v in news.values())

    async def test_a_failed_power_up_is_refunded(self):
        wallet = Wallet({(1, "steal"): 1})
        hub, room, host, guest, anon, conns = await live_game(wallet)
        await hub.handle_message(room, host, conns[host], {"t": "boost", "item": "steal", "target": host})
        assert "bad_target" in conns[host].errors() and wallet.owned[(1, "steal")] == 1
        for bad in ({"item": "gold"}, {"item": None}, {"item": "steal", "target": 5}):
            await hub.handle_message(room, host, conns[host], {"t": "boost", **bad})
        assert wallet.owned[(1, "steal")] == 1

        # Paid for, but the game moves on before it lands: the power-up comes back.
        async def spend_while_the_game_ends(uid, item):
            ok = await wallet.spend(uid, item)
            room.game_no += 1
            return ok

        hub.spend_powerup = spend_while_the_game_ends
        with contextlib.suppress(HubError):
            await hub._use_boost(room, host, {"item": "steal", "target": guest})
        assert wallet.owned[(1, "steal")] == 1
