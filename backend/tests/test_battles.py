"""Battle prizes: duel and group payouts, shared places, leavers, the daily limit."""

from __future__ import annotations

import unittest
import unittest.mock
from datetime import date, timedelta

from app import battles as B

FORMAT_OF = B.format_of  # the real rotation (the tests below pin it)


def setUpModule():  # noqa: N802 - the unittest hook
    """Pin the week's featured battle format to one these tests never play (Battleships duels), so
    prizes are the usual ones whatever the date."""
    global _pin
    _pin = unittest.mock.patch.object(B, "format_of", lambda day: "fleet")
    _pin.start()


def tearDownModule():  # noqa: N802
    _pin.stop()


class PrizeTests(unittest.TestCase):
    def test_a_duel(self):
        self.assertEqual(B.prizes("duel", {1: 1, 2: 2}, {1, 2}), {1: B.DUEL_PRIZE, 2: B.FINISH_PRIZE})
        draw = B.prizes("duel", {1: 1, 2: 1}, {1, 2})
        self.assertEqual(draw, {1: B.DUEL_PRIZE // 2, 2: B.DUEL_PRIZE // 2})
        self.assertLessEqual(sum(draw.values()), B.DUEL_PRIZE + B.FINISH_PRIZE)  # a draw never pays more

    def test_a_group_and_leavers(self):
        got = B.prizes("group", {1: 1, 2: 1, 3: 3, 4: 4}, {1, 2, 3})
        self.assertEqual(got, {1: B.GROUP_PRIZE, 2: B.GROUP_PRIZE, 3: B.FINISH_PRIZE, 4: 0})

    def test_the_daily_limit(self):
        self.assertEqual(B.limited(B.DAILY_PRIZES - 1, 40), 40)
        self.assertEqual(B.limited(B.DAILY_PRIZES, 40), 0)

    def test_the_featured_format(self):
        monday = date(2026, 10, 26)
        self.assertEqual(
            {FORMAT_OF(monday + timedelta(days=d)) for d in range(7)}, {FORMAT_OF(monday)}
        )  # all week
        self.assertEqual(
            {FORMAT_OF(monday + timedelta(weeks=w)) for w in range(len(B.FORMATS))}, set(B.FORMATS)
        )
        self.assertTrue(B.featured("speed", "duel", "four"))
        self.assertFalse(B.featured("speed", "group", "four"))
        self.assertTrue(B.featured("crowd", "group", "imposter"))  # any game
        self.assertFalse(B.featured("chess", "duel", "four"))
        got = B.prizes("duel", {1: 1, 2: 2}, {1, 2}, bonus=True)
        self.assertEqual(got, {1: int(B.DUEL_PRIZE * B.FEATURE_BONUS), 2: B.FINISH_PRIZE})  # winners only
        draw = B.prizes("duel", {1: 1, 2: 1}, {1, 2}, bonus=True)
        self.assertEqual(sum(draw.values()), int(B.DUEL_PRIZE * B.FEATURE_BONUS))


# -- storage: payouts, limits, the record ----------------------------------------------------------
import asyncio  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

from sqlalchemy import update  # noqa: E402

from app import fairplay as F  # noqa: E402
from app.db import Database, User  # noqa: E402


class StoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database("sqlite+aiosqlite:///:memory:")
        await self.db.init()
        self.ids = [(await self.db.create_user(n, "x", "y")).id for n in ("Ana_99", "Bo_42", "Cy_7", "Di_5")]
        await self.trust(self.ids)

    async def trust(self, ids):
        """Old enough, with a confirmed email: allowed to win battle prizes."""
        async with self.db.sessions() as s:
            old = datetime.now(UTC) - timedelta(days=F.NEW_ACCOUNT_DAYS + 1)
            await s.execute(update(User).where(User.id.in_(ids)).values(created_at=old, email_verified=True))
            await s.commit()

    async def duel(self, a, b, a_place=1, b_place=2):
        bid = await self.db.create_battle(None, "ABCD", "four", "duel", a, b)
        return await self.db.settle_battle(bid, {a: a_place, b: b_place}, {a, b})

    async def test_a_duel_pays_once_and_the_same_pair_stops_paying(self):
        a, b, *_ = self.ids
        bid = await self.db.create_battle(None, "ABCD", "four", "duel", a, b)
        paid = await self.db.settle_battle(bid, {a: 1, b: 2}, {a, b})
        self.assertEqual((paid[a]["prize"], paid[b]["prize"]), (B.DUEL_PRIZE, B.FINISH_PRIZE))
        self.assertIsNone(await self.db.settle_battle(bid, {a: 1, b: 2}, {a, b}))  # once
        for _ in range(F.BATTLE_REPEAT_LIMIT - 1):
            await self.duel(a, b)
        paid = await self.duel(b, a, 2, 1)  # who challenged whom doesn't matter: the same two
        self.assertEqual((paid[a]["prize"], paid[a]["note"]), (0, "repeat"))
        record = await self.db.battle_record(a)
        n = F.BATTLE_REPEAT_LIMIT + 1
        self.assertEqual((record["played"], record["trophies"]), (n, n))
        self.assertEqual(record["head_to_head"], [{"username": "Bo_42", "won": n, "lost": 0, "drawn": 0}])
        self.assertEqual(record["prizes"], B.DUEL_PRIZE * F.BATTLE_REPEAT_LIMIT)

    async def test_the_daily_limit_same_device_and_leavers(self):
        a, b, c, d = self.ids
        for i in range(B.DAILY_PRIZES):
            other = (await self.db.create_user(f"Op_{i}", "x", "y")).id
            await self.trust([other])
            await self.duel(a, other)
        paid = await self.duel(a, b)
        self.assertEqual(paid[a]["note"], "limit")
        await self.db.note_device(c, "same-browser")
        await self.db.note_device(d, "same-browser")
        paid = await self.duel(c, d)
        self.assertEqual({r["note"] for r in paid.values()}, {"device"})
        bid = await self.db.create_battle(None, "ABCD", "trivia", "group", b, None)
        paid = await self.db.settle_battle(bid, {b: 1, c: 2, d: 3}, {b, c})
        self.assertEqual(
            {u: (r["prize"], r["note"]) for u, r in paid.items()},
            {b: (B.GROUP_PRIZE, ""), c: (0, "device"), d: (0, "left")},
        )

    async def test_challenges_waiting(self):
        a, b, *_ = self.ids
        await self.db.create_battle(None, "WXYZ", "chess", "duel", a, b)
        waiting = (await self.db.battle_record(b))["challenges"]
        self.assertEqual([(c["by"], c["room"]) for c in waiting], [("Ana_99", "WXYZ")])


# -- the room: the battle game first, the right players, prizes on the results ----------------------
from tests.test_ranked import room_of  # noqa: E402


class RoomTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_duel_room(self):
        paid = []

        async def on_battle(bid, placing, finished, quick):
            paid.append((bid, placing, finished, quick))
            return {u: {"place": p, "prize": 40 if p == 1 else 10, "note": ""} for u, p in placing.items()}

        hub, room, pids, conns = await room_of(3)
        hub.on_battle = on_battle
        hub.set_battle(room, 7, "four", "duel", [1, 2])
        await hub.handle_message(room, pids[0], conns[pids[0]], {"t": "start", "game": "chess"})
        self.assertIn("battle_game", conns[pids[0]].errors())
        await hub.handle_message(room, pids[0], conns[pids[0]], {"t": "start", "game": "four"})
        self.assertIn("battle_players", conns[pids[0]].errors())  # a third player is here
        await hub.disconnect(room, pids[2], conns[pids[2]])
        await hub.handle_message(room, pids[0], conns[pids[0]], {"t": "start", "game": "four"})
        self.assertEqual(room.game.game_id, "four")
        await hub.handle_message(room, pids[0], conns[pids[0]], {"t": "boost", "item": "double"})
        self.assertIn("battle", conns[pids[0]].errors())  # no power-ups in a battle
        self.assertEqual(hub.view_for(room, pids[0])["battle"]["kind"], "duel")
        room.game.scores = lambda: {pids[0]: 0, pids[1]: 300}
        room.game.finished = True
        room.game_began -= 60  # played long enough to count
        hub._maybe_finish(room)
        await asyncio.gather(*list(hub._tasks))
        self.assertEqual(paid, [(7, {1: 2, 2: 1}, {1, 2}, False)])
        self.assertEqual(hub.view_for(room, pids[1])["battle"]["news"][pids[1]]["prize"], 40)
        self.assertEqual(room.battle, {})  # played: the room goes on as a normal one
        self.assertIsNone(hub.view_for(room, pids[1])["battle"]["game"])


# -- HTTP ---------------------------------------------------------------------------------------------
import pytest  # noqa: E402

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from tests.test_api import settings  # noqa: E402

PW = "correct horse battery"


def be(client, name):
    client.cookies.clear()  # each person on their own browser
    if client.post("/api/auth/login", json={"username": name, "password": PW}).status_code != 200:
        assert client.post("/api/auth/signup", json={"username": name, "password": PW}).status_code == 201


def test_challenges_over_http(tmp_path):
    with TestClient(create_app(settings(tmp_path, rate_auth_burst=1000))) as client:
        be(client, "Ana_99")
        slug = client.post("/api/clubs", json={"name": "Hostel Four"}).json()["slug"]
        code = client.post(f"/api/clubs/{slug}/invites", json={}).json()["code"]
        be(client, "Bo_42")
        client.post("/api/clubs/join", json={"code": code})
        be(client, "Ana_99")
        url = f"/api/clubs/{slug}/battles"
        bad = [
            ({"kind": "duel", "game": "four", "opponent": "Nobody"}, 404),
            ({"kind": "duel", "game": "four", "opponent": "Ana_99"}, 404),
            ({"kind": "duel", "game": "imposter", "opponent": "Bo_42"}, 400),
            ({"kind": "group", "game": "nope"}, 400),
            ({"kind": "brawl", "game": "four"}, 400),
        ]
        for body, status in bad:
            assert client.post(url, json={"name": "Ana", **body}).status_code == status, body
        r = client.post(url, json={"name": "Ana", "kind": "duel", "game": "four", "opponent": "bo_42"})
        assert r.status_code == 201, r.text
        room = r.json()["code"]
        be(client, "Bo_42")
        inbox = client.get("/api/notifications").json()["items"]
        assert inbox[0]["kind"] == "battle" and inbox[0]["link"] == f"/r/{room}"
        record = client.get("/api/me/battles").json()
        assert record["challenges"][0]["by"] == "Ana_99" and record["challenges"][0]["open"] is True
        now = client.get("/api/me/happening").json()  # the home page's "Happening now"
        assert now["challenges"] == 1
        assert now["rooms"] == []  # nobody is in the room yet: only rooms with someone in them show
        assert client.post(url, json={"name": "Bo", "kind": "group", "game": "imposter"}).status_code == 201
        # the same browser for two accounts: no duel
        client.post("/api/auth/logout")
        client.post("/api/auth/login", json={"username": "Ana_99", "password": PW})
        r = client.post(url, json={"name": "Ana", "kind": "duel", "game": "four", "opponent": "Bo_42"})
        assert r.status_code == 403 and r.json()["error"]["code"] == "same_device"
