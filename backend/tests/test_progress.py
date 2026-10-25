"""Levels and daily quests: the XP curve, and three quests a day (one social) that stay put all day."""

from __future__ import annotations

import unittest
from datetime import date

from app import progress as P


class LevelTests(unittest.TestCase):
    def test_the_curve(self):
        self.assertEqual([P.xp_for(n) for n in (1, 2, 3, 4)], [0, 100, 300, 600])
        for xp, level in ((0, 1), (99, 1), (100, 2), (299, 2), (300, 3), (599, 3), (600, 4), (10**6, 141)):
            self.assertEqual(P.level_of(xp), level, xp)


class QuestTests(unittest.TestCase):
    def test_three_a_day_one_social_stable_and_varied(self):
        day = date(2026, 10, 25)
        picks = P.daily_quests(7, day)
        self.assertEqual(len(picks), 3)
        self.assertEqual(len(set(picks)), 3)
        self.assertTrue(P.QUESTS[picks[0]]["social"])
        self.assertTrue(all(not P.QUESTS[q]["social"] for q in picks[1:]))
        self.assertEqual(P.daily_quests(7, day), picks)  # the same all day
        days = {tuple(P.daily_quests(7, date(2026, 10, d))) for d in range(1, 29)}
        self.assertGreater(len(days), 5)  # and different across days


if __name__ == "__main__":
    unittest.main()


# -- storage: XP from fair games, levels, connections, quests -----------------------------------------
import unittest.mock  # noqa: E402

from app import fairplay as F  # noqa: E402
from app.db import Database, Result  # noqa: E402


def finish(uid, place, group, accounts=2, note=""):
    return {
        "user_id": uid,
        "game_id": "four",
        "place": place,
        "players": 2,
        "points": 300,
        "coins": 50 if place == 1 else 30,
        "group": group,
        "accounts": accounts,
        "note": note,
    }


class StoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database("sqlite+aiosqlite:///:memory:")
        await self.db.init()
        self.ids = [(await self.db.create_user(f"Q{i}_00", "x", "y")).id for i in range(4)]

    async def game(self, winner, loser, **kw):
        g = F.group_key([winner, loser])
        return await self.db.record_results([finish(winner, 1, g, **kw), finish(loser, 2, g, **kw)], "s", 600)

    async def test_xp_only_from_fair_games(self):
        a, b, *_ = self.ids
        paid = await self.game(a, b)
        self.assertEqual(paid[a]["xp"], P.XP_FINISH + P.XP_WIN + P.XP_FIRST_WIN)
        self.assertEqual(paid[b]["xp"], P.XP_FINISH)
        paid = await self.game(a, b)
        self.assertEqual(paid[a]["xp"], P.XP_FINISH + P.XP_WIN)  # the first-win bonus is once a day
        for note in ("quick", "device", "solo"):
            paid = await self.game(a, b, note=note)
            self.assertEqual({p["xp"] for p in paid.values()}, {0}, note)
        paid = await self.game(a, b, accounts=1)
        self.assertEqual({p["xp"] for p in paid.values()}, {0})
        async with self.db.sessions() as s:
            fair = (await s.execute(Result.__table__.select().where(Result.user_id == a))).all()
        self.assertEqual([r.fair for r in fair], [True, True, False, False, False, False])

    async def test_the_daily_cap_and_level_ups(self):
        a, *rest = self.ids
        others = [(await self.db.create_user(f"Z{i}_00", "x", "y")).id for i in range(40)]
        total = 0
        for o in others:  # new opponents each time, so the repeat rule never applies
            total += (await self.game(a, o))[a]["xp"]
        self.assertEqual(total, P.XP_DAILY_CAP)
        progress = await self.db.progress(a)
        self.assertEqual((progress["xp"], progress["today_xp"]), (P.XP_DAILY_CAP, P.XP_DAILY_CAP))
        self.assertEqual(progress["level"], P.level_of(P.XP_DAILY_CAP))
        user = await self.db.user_by_id(a)
        gifts = sum(user.powerups.values())
        self.assertEqual(gifts, progress["level"] - 1)  # a power-up for every level reached
        history = await self.db.coin_history(a)
        self.assertEqual(sum(1 for e in history["entries"] if e["reason"] == "level"), progress["level"] - 1)

    async def test_quests_from_real_play_claimed_once(self):
        a, b, c, d = self.ids
        with unittest.mock.patch.object(
            P, "daily_quests", lambda uid, day: ["three_people", "finish3", "win1"]
        ):
            progress = await self.db.progress(a)
            self.assertEqual([q["progress"] for q in progress["quests"]], [0, 0, 0])
            self.assertEqual(await self.db.claim_quest(a, "win1"), "not_done")
            await self.game(a, b)
            await self.game(c, a)
            await self.game(a, d)
            progress = await self.db.progress(a)
            self.assertEqual(
                [(q["progress"], q["target"]) for q in progress["quests"]], [(3, 3), (3, 3), (1, 1)]
            )
            before = (await self.db.user_by_id(a)).xp
            self.assertEqual(await self.db.claim_quest(a, "win1"), "")
            self.assertEqual(await self.db.claim_quest(a, "win1"), "claimed")
            self.assertEqual(await self.db.claim_quest(a, "battle1"), "not_today")
            self.assertEqual((await self.db.user_by_id(a)).xp, before + P.XP_QUEST)
            history = await self.db.coin_history(a)
            self.assertEqual(
                [e["delta"] for e in history["entries"] if e["reason"] == "quest"], [P.QUEST_COINS]
            )
            self.assertTrue(
                next(q for q in (await self.db.progress(a))["quests"] if q["id"] == "win1")["claimed"]
            )

    async def test_new_people_and_clubmates(self):
        a, b, c, _ = self.ids
        with unittest.mock.patch.object(
            P, "daily_quests", lambda uid, day: ["new_person", "new_clubmate", "win1"]
        ):
            await self.game(a, b, note="quick")  # an unfair game makes no connection
            self.assertEqual((await self.db.progress(a))["quests"][0]["progress"], 0)
            await self.game(a, b)
            progress = await self.db.progress(a)
            self.assertEqual([q["progress"] for q in progress["quests"][:2]], [1, 0])  # b isn't a clubmate


# -- HTTP ----------------------------------------------------------------------------------------------
import pytest  # noqa: E402

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from tests.test_api import settings  # noqa: E402

PW = "correct horse battery"


def be(client, name):
    client.cookies.clear()
    if client.post("/api/auth/login", json={"username": name, "password": PW}).status_code != 200:
        assert client.post("/api/auth/signup", json={"username": name, "password": PW}).status_code == 201


def test_progress_and_a_clubmate_quest_over_http(tmp_path):
    with TestClient(create_app(settings(tmp_path, rate_auth_burst=1000))) as client:
        be(client, "Ana_99")
        slug = client.post("/api/clubs", json={"name": "Hostel Four"}).json()["slug"]
        code = client.post(f"/api/clubs/{slug}/invites", json={}).json()["code"]
        be(client, "Bo_42")
        client.post("/api/clubs/join", json={"code": code})
        be(client, "Ana_99")
        db = client.app.state.db
        ana, bo = (client.portal.call(db.user_by_name, n).id for n in ("Ana_99", "Bo_42"))
        with unittest.mock.patch.object(
            P, "daily_quests", lambda uid, day: ["new_clubmate", "win1", "finish3"]
        ):
            body = client.get("/api/me/progress").json()
            assert body["level"] == 1 and [q["id"] for q in body["quests"]] == [
                "new_clubmate",
                "win1",
                "finish3",
            ]
            r = client.post("/api/me/quests/new_clubmate/claim")
            assert r.status_code == 409 and r.json()["error"]["code"] == "not_done"
            g = F.group_key([ana, bo])
            client.portal.call(db.record_results, [finish(ana, 1, g), finish(bo, 2, g)], "s", 600)
            body = client.post("/api/me/quests/new_clubmate/claim").json()
            assert next(q for q in body["quests"] if q["id"] == "new_clubmate")["claimed"] is True
            assert client.post("/api/me/quests/ranked1/claim").status_code == 404
        client.cookies.clear()
        assert client.get("/api/me/progress").status_code == 401
