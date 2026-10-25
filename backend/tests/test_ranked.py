"""Ranked play: who can start a ranked game, rating it from the server's final scores (leavers placed
last), power-ups off; storage (season, day cap, same-pair limit); and the HTTP routes (your ratings,
boards for everyone, a club, a place, this week; the place-board choice)."""

from __future__ import annotations

import asyncio
import random
import unittest
from datetime import UTC, datetime, timedelta

import pytest

from app import ratings as R
from app.config import Settings
from app.db import Database, RatingEvent, SkillRating
from app.rooms import Hub
from tests.test_rooms import FakeConn


class Rater:
    def __init__(self, answer=None):
        self.calls: list[tuple[str, dict[int, int]]] = []
        self.answer = answer

    async def __call__(self, game_id, placing):
        self.calls.append((game_id, dict(placing)))
        if self.answer == "uncounted":
            return None
        return {
            u: {"before": 1000, "after": 1000 + (20 if p == 1 else -20), "games": 1, "tier": "Provisional"}
            for u, p in placing.items()
        }


async def room_of(n_accounts: int, guests: int = 0, rater: Rater | None = None):
    hub = Hub(Settings(secret_key="s" * 40), rng=random.Random(1), intro_seconds=0, on_rated=rater)
    room, host, _ = hub.create_room("Host", user_id=1)
    conns = {host.id: FakeConn()}
    pids = [host.id]
    for i in range(1, n_accounts):
        _, p, _ = hub.join_room(room.code, f"P{i}", user_id=i + 1)
        pids.append(p.id)
    for i in range(guests):
        _, p, _ = hub.join_room(room.code, f"G{i}")
        pids.append(p.id)
    for pid in pids:
        conns.setdefault(pid, FakeConn())
        await hub.connect(room, pid, conns[pid])
    return hub, room, pids, conns


async def start(hub, room, pids, conns, game="four", **extra):
    await hub.handle_message(
        room, pids[0], conns[pids[0]], {"t": "start", "game": game, "ranked": True, **extra}
    )
    return conns[pids[0]].errors()


class HubTests(unittest.IsolatedAsyncioTestCase):
    async def test_who_can_start_a_ranked_game(self):
        hub, room, pids, conns = await room_of(2, guests=1)
        self.assertIn("ranked_guests", await start(hub, room, pids, conns))
        hub, room, pids, conns = await room_of(1)
        self.assertIn("too_few", await start(hub, room, pids, conns))
        hub, room, pids, conns = await room_of(2)
        self.assertIn("too_few", await start(hub, room, pids, conns, game="trivia"))  # 3 for free-for-all
        self.assertIn("not_ranked", await start(hub, room, pids, conns, game="rather"))
        self.assertIn("ranked_teams", await start(hub, room, pids, conns, game="four", teams=True))
        hub, room, pids, conns = await room_of(2)
        self.assertEqual(await start(hub, room, pids, conns), [])
        self.assertTrue(room.ranked and room.game is not None)
        self.assertTrue(hub.view_for(room, pids[1])["ranked"]["on"])

    async def test_ranked_uses_standard_options_and_no_power_ups(self):
        hub, room, pids, conns = await room_of(3)
        self.assertEqual(await start(hub, room, pids, conns, game="trivia", options={"questions": "5"}), [])
        self.assertTrue(room.ranked)
        self.assertEqual(room.game.options, {})  # the host's choice is set aside: standard settings
        await hub.handle_message(room, pids[0], conns[pids[0]], {"t": "boost", "item": "double"})
        self.assertIn("ranked", conns[pids[0]].errors())

    async def test_rated_from_final_scores_and_leavers_lose(self):
        rater = Rater()
        hub, room, pids, conns = await room_of(3, rater=rater)
        await start(hub, room, pids, conns, game="trivia")
        game = room.game
        game.scores = lambda: {pids[0]: 5, pids[1]: 9, pids[2]: 12}
        game.finished = True
        await hub.disconnect(room, pids[2], conns[pids[2]])  # the top scorer walked out
        hub._maybe_finish(room)
        await asyncio.gather(*list(hub._tasks))
        self.assertEqual(rater.calls, [("trivia", {1: 2, 2: 1, 3: 3})])
        news = hub.view_for(room, pids[0])["ranked"]["news"]
        self.assertEqual(news[pids[1]]["after"], 1020)
        self.assertTrue(all(n["counted"] for n in news.values()))

    async def test_an_uncounted_game_says_so_and_unranked_games_are_not_rated(self):
        rater = Rater("uncounted")
        hub, room, pids, conns = await room_of(2, rater=rater)
        await start(hub, room, pids, conns)
        room.game.scores = lambda: {pids[0]: 1, pids[1]: 0}
        room.game.finished = True
        hub._maybe_finish(room)
        await asyncio.gather(*list(hub._tasks))
        self.assertEqual(
            {n["counted"] for n in hub.view_for(room, pids[0])["ranked"]["news"].values()}, {False}
        )

        rater = Rater()
        hub, room, pids, conns = await room_of(2, rater=rater)
        await hub.handle_message(room, pids[0], conns[pids[0]], {"t": "start", "game": "four"})
        room.game.scores = lambda: {pids[0]: 1, pids[1]: 0}
        room.game.finished = True
        hub._maybe_finish(room)
        await asyncio.gather(*list(hub._tasks))
        self.assertEqual(rater.calls, [])


class StoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database("sqlite+aiosqlite:///:memory:")
        await self.db.init()
        self.ids = []
        for name in ("Ana_99", "Bo_42", "Cy_7"):
            user = await self.db.create_user(name, "x", "y")
            self.ids.append(user.id)

    async def test_a_rated_game_and_the_season(self):
        a, b, c = self.ids
        out = await self.db.rate_match("trivia", {a: 1, b: 2, c: 3})
        self.assertGreater(out[a]["after"], out[a]["before"])
        self.assertLess(out[c]["after"], out[c]["before"])
        self.assertEqual(out[a]["tier"], "Provisional")
        mine = {r["game"]: r for r in await self.db.my_ratings(a)}
        self.assertEqual(mine["trivia"]["games"], 1)
        # last season's rating comes back halfway to the start
        async with self.db.sessions() as s:
            row = await s.get(SkillRating, (a, "trivia"))
            row.season, row.mu, row.sigma = R.season_of() - 1, 35.0, 3.0
            await s.commit()
        mine = {r["game"]: r for r in await self.db.my_ratings(a)}
        self.assertEqual(mine["trivia"]["rating"], R.soft_reset(R.Rating(35, 3), 1).display)

    async def test_the_same_pair_stops_counting_and_the_day_is_capped(self):
        a, b, _ = self.ids
        for _ in range(R.PAIR_LIMIT):
            self.assertIsNotNone(await self.db.rate_match("four", {a: 1, b: 2}))
        self.assertIsNone(await self.db.rate_match("four", {a: 1, b: 2}))
        async with self.db.sessions() as s:  # a day later they count again
            for ev in (await s.execute(RatingEvent.__table__.select())).all():
                await s.execute(
                    RatingEvent.__table__.update()
                    .where(RatingEvent.id == ev.id)
                    .values(at=datetime.now(UTC) - timedelta(days=2))
                )
            await s.commit()
        self.assertIsNotNone(await self.db.rate_match("four", {a: 1, b: 2}))
        moved = 0
        for _ in range(30):  # a long winning day across fresh opponents never passes the cap
            other = await self.db.create_user(f"Op_{moved}_{_}", "x", "y")
            got = await self.db.rate_match("chess", {a: 1, other.id: 2})
            moved = got[a]["after"] - 1000 if got else moved
        self.assertLessEqual(moved, R.DAY_CAP)
        self.assertGreater(moved, R.DAY_CAP - 30)


# -- HTTP -------------------------------------------------------------------------------------------
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from tests.test_api import settings  # noqa: E402

PW = "correct horse battery"


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(settings(tmp_path, rate_auth_burst=1000))) as c:
        yield c


def signup(client, name):
    r = client.post("/api/auth/signup", json={"username": name, "password": PW})
    assert r.status_code == 201, r.text


def login(client, name):
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"username": name, "password": PW}).status_code == 200


def play(client, game, placing_by_name, times=1):
    db = client.app.state.db
    ids = {}
    for name in placing_by_name:
        ids[name] = client.portal.call(db.user_by_name, name).id
    for _ in range(times):
        client.portal.call(db.rate_match, game, {ids[n]: p for n, p in placing_by_name.items()})


def test_ratings_and_boards(client):
    for name in ("Ana_99", "Bo_42", "Cy_7"):
        signup(client, name)
    assert client.get("/api/ratings/me").status_code == 200  # Cy is signed in
    for _ in range(R.PROVISIONAL_GAMES):
        play(client, "trivia", {"Ana_99": 1, "Bo_42": 2, "Cy_7": 3})
    me = client.get("/api/ratings/me").json()
    trivia = next(g for g in me["games"] if g["game"] == "trivia")
    assert trivia["games"] == R.PROVISIONAL_GAMES and trivia["placement_left"] == 0
    assert trivia["tier"] != "Provisional" and me["place_boards"] is False
    assert next(g for g in me["games"] if g["game"] == "chess")["tier"] == "Provisional"

    board = client.get("/api/ratings/board?game=trivia").json()
    assert [r["username"] for r in board["rows"]] == ["Ana_99", "Bo_42", "Cy_7"]
    assert board["rows"][2]["you"] is True
    week = client.get("/api/ratings/board?game=trivia&period=week").json()
    assert week["rows"][0]["gain"] > 0 and week["rows"][-1]["gain"] < 0
    for bad in ("game=rather", "game=trivia&scope=galaxy", "game=trivia&period=year"):
        assert client.get(f"/api/ratings/board?{bad}").status_code == 404

    # a club's board: members only
    login(client, "Ana_99")
    club = client.post("/api/clubs", json={"name": "Owls"}).json()
    slug = club["slug"] if "slug" in club else club["club"]["slug"]
    rows = client.get(f"/api/ratings/board?game=trivia&scope=club&slug={slug}").json()["rows"]
    assert [r["username"] for r in rows] == ["Ana_99"]
    login(client, "Bo_42")
    assert client.get(f"/api/ratings/board?game=trivia&scope=club&slug={slug}").status_code == 404
    assert client.get("/api/ratings/board?game=trivia&scope=place&slug=nowhere").status_code == 404

    assert client.post("/api/me/place-boards", json={"on": True}).json() == {"ok": True}
    assert client.get("/api/ratings/me").json()["place_boards"] is True
    client.cookies.clear()
    assert client.get("/api/ratings/me").status_code == 401
