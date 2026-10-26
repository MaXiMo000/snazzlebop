"""Levels and daily quests: the XP curve, and three quests a day (one social) that stay put all day."""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime, timedelta

from app import progress as P


class LevelTests(unittest.TestCase):
    def test_the_curve(self):
        self.assertEqual([P.xp_for(n) for n in (1, 2, 3, 4)], [0, 100, 300, 600])
        for xp, level in ((0, 1), (99, 1), (100, 2), (299, 2), (300, 3), (599, 3), (600, 4), (10**6, 141)):
            self.assertEqual(P.level_of(xp), level, xp)


class QuestTests(unittest.TestCase):
    def test_every_kind_holds_a_week_and_measures_are_known(self):
        measures = {
            "fair_games", "wins", "top2", "big_games", "big_wins", "distinct_games", "category", "categories",
            "new_games", "ranked", "ranked_wins", "battles", "battle_wins", "new_people", "people",
            "old_friends", "clubmates", "new_clubmates", "activity", "coins_earned", "xp_earned", "shop",
        }  # fmt: skip
        for kind in P.KINDS:
            self.assertGreaterEqual(sum(q["kind"] == kind for q in P.QUESTS.values()), 7, kind)
        self.assertGreaterEqual(len(P.QUESTS), 40)
        for qid, q in {**P.QUESTS, **P.WEEKLY}.items():
            self.assertIn(q["measure"], measures, qid)
            self.assertIn(q["kind"], P.KINDS, qid)

    def test_three_a_day_one_social_no_repeats_within_a_week(self):
        for user in (1, 7, 42, 999):
            history = []
            for d in range(60):
                day = date(2026, 3, 1) + timedelta(days=d)
                picks = P.daily_quests(user, day)
                self.assertEqual(P.daily_quests(user, day), picks)  # the same all day
                kinds = [P.QUESTS[x]["kind"] for x in picks]
                self.assertEqual(kinds[0], "social")
                self.assertEqual(len(set(kinds)), 3)  # three different kinds
                for earlier in history[-6:]:
                    self.assertFalse(set(picks) & set(earlier), f"repeat within a week for {user} on {day}")
                history.append(picks)

    def test_rerolls_and_weekly_challenges(self):
        day = date(2026, 10, 25)
        picks = P.daily_quests(7, day)
        for qid in picks:
            new = P.reroll_for(7, day, qid)
            self.assertNotIn(new, picks)
            self.assertEqual(P.QUESTS[new]["kind"], P.QUESTS[qid]["kind"])
        week = P.weekly_challenges(7, day)
        self.assertEqual(len(set(week)), 3)
        monday = P.week_start(day)
        for d in range(7):
            self.assertEqual(P.weekly_challenges(7, monday + timedelta(days=d)), week)  # all week
        self.assertNotEqual(P.weekly_challenges(7, monday + timedelta(days=7)), week)


if __name__ == "__main__":
    unittest.main()


# -- storage: XP from fair games, levels, connections, quests -----------------------------------------
import unittest.mock  # noqa: E402

from app import fairplay as F  # noqa: E402
from app.db import Database, Result, XpEvent  # noqa: E402


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


class VarietyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database("sqlite+aiosqlite:///:memory:")
        await self.db.init()
        self.ids = [(await self.db.create_user(f"V{i}_00", "x", "y")).id for i in range(3)]

    async def game(self, winner, loser, game_id="four"):
        g = F.group_key([winner, loser])
        rows = [finish(winner, 1, g), finish(loser, 2, g)]
        for r in rows:
            r["game_id"] = game_id
        return await self.db.record_results(rows, "s", 600)

    async def test_activity_and_category_quests(self):
        a, b, _ = self.ids
        with unittest.mock.patch.object(
            P, "daily_quests", lambda uid, day: ["new_person", "cat_quiz", "use_party"]
        ):
            await self.game(a, b, "trivia")
            await self.db.log_activity([a], "party")
            progress = await self.db.progress(a)
            self.assertEqual([q["progress"] for q in progress["quests"]], [1, 1, 1])
            self.assertEqual([q["kind"] for q in progress["quests"]], ["social", "games", "fun"])

    async def test_one_reroll_a_day_never_after_claiming(self):
        a, b, _ = self.ids
        with unittest.mock.patch.object(
            P, "daily_quests", lambda uid, day: ["new_person", "win1", "use_party"]
        ):
            await self.game(a, b)
            self.assertEqual(await self.db.claim_quest(a, "win1"), "")
            self.assertEqual(await self.db.reroll_quest(a, "win1"), "claimed")
            self.assertEqual(await self.db.reroll_quest(a, "use_party"), "")
            progress = await self.db.progress(a)
            ids = [q["id"] for q in progress["quests"]]
            self.assertNotIn("use_party", ids)
            self.assertEqual(P.QUESTS[ids[2]]["kind"], "fun")
            self.assertFalse(progress["reroll_left"])
            self.assertEqual(await self.db.reroll_quest(a, "new_person"), "rerolled")

    async def test_the_streak_bonus_every_seventh_day(self):
        a, b, _ = self.ids
        today = self.db._today()
        async with self.db.sessions() as s:  # six earlier days, all three claimed
            for d in range(1, P.STREAK_DAYS):
                day = (today - timedelta(days=d)).date().isoformat()
                for qid in ("x", "y", "z"):
                    s.add(XpEvent(user_id=a, delta=1, reason="quest", ref=f"{day}:{qid}"))
            await s.commit()
        with unittest.mock.patch.object(
            P, "daily_quests", lambda uid, day: ["new_person", "win1", "finish3"]
        ):
            for _ in range(3):
                await self.game(a, b)
            for qid in ("new_person", "win1"):
                self.assertEqual(await self.db.claim_quest(a, qid), "")
            self.assertEqual((await self.db.progress(a))["streak"], P.STREAK_DAYS - 1)
            self.assertEqual(await self.db.claim_quest(a, "finish3"), "")
            self.assertEqual((await self.db.progress(a))["streak"], P.STREAK_DAYS)
        history = await self.db.coin_history(a)
        self.assertEqual(
            [e["delta"] for e in history["entries"] if e["reason"] == "streak"], [P.STREAK_COINS]
        )
        self.assertEqual((await self.db.user_by_id(a)).powerups.get(P.STREAK_GIFT), 1)

    async def test_weekly_challenges(self):
        a, b, c = self.ids
        with unittest.mock.patch.object(
            P, "weekly_challenges", lambda uid, day: ["w_win10", "w_people8", "w_cats4"]
        ):
            self.assertEqual(await self.db.claim_weekly(a, "w_win10"), "not_done")
            self.assertEqual(await self.db.claim_weekly(a, "w_ranked5"), "not_today")
            for game in ("trivia", "dice", "chicken"):
                await self.game(a, b, game)
            await self.game(a, c, "four")
            weekly = (await self.db.progress(a))["weekly"]
            self.assertEqual([w["progress"] for w in weekly["challenges"]], [4, 2, 4])
            self.assertEqual(await self.db.claim_weekly(a, "w_cats4"), "")
            self.assertEqual(await self.db.claim_weekly(a, "w_cats4"), "claimed")
            self.assertTrue((await self.db.progress(a))["weekly"]["challenges"][2]["claimed"])


class SeasonChallengeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database("sqlite+aiosqlite:///:memory:")
        await self.db.init()
        self.ids = [(await self.db.create_user(f"S{i}_00", "x", "y")).id for i in range(2)]

    async def test_claims_once_and_the_badge_needs_all_five(self):
        from app import ratings as R

        a, _ = self.ids
        season = R.season_of(self.db._today())
        self.assertEqual(await self.db.claim_season(a, "s_ranked20"), "not_done")
        self.assertEqual(await self.db.claim_season(a, "nope"), "not_today")
        with unittest.mock.patch.object(self.db, "_measure", lambda *args: _done(100)):
            for cid in list(P.SEASON)[:-1]:
                self.assertEqual(await self.db.claim_season(a, cid), "")
            self.assertEqual(await self.db.claim_season(a, cid), "claimed")
            view = (await self.db.progress(a))["season"]
            self.assertEqual(view["badges"], [])  # four of five
            self.assertEqual(await self.db.claim_season(a, list(P.SEASON)[-1]), "")
            view = (await self.db.progress(a))["season"]
        self.assertEqual((view["season"], view["badges"]), (season, [season]))
        self.assertTrue(all(c["claimed"] for c in view["challenges"]))
        history = await self.db.coin_history(a)
        self.assertEqual(
            sum(e["delta"] for e in history["entries"] if e["reason"] == "season_ch"), 5 * P.SEASON_COINS
        )

    async def test_battles_that_paid_nothing_for_farming_dont_count(self):
        from app.db import Battle, BattleResult

        a, b = self.ids
        async with self.db.sessions() as s:
            for note in ("", "repeat", "device", "quick"):
                battle = Battle(room_code="X", game_id="four", kind="duel", challenger_id=a, status="played")
                battle.played_at = datetime.now(UTC)
                s.add(battle)
                await s.flush()
                s.add(BattleResult(battle_id=battle.id, user_id=a, place=1, prize=0, note=note))
            await s.commit()
            got = await self.db._measure(s, a, P.SEASON["s_battles10"], datetime.now(UTC) - timedelta(days=1))
        self.assertEqual(got, 1)


async def _done(n):
    return n


class ClubChallengeRuleTests(unittest.TestCase):
    def test_one_a_week_sized_to_the_club(self):
        monday = date(2026, 10, 5)
        week = [P.club_challenge(3, monday + timedelta(days=d)) for d in range(7)]
        self.assertEqual(len(set(week)), 1)  # the same all week
        seen = {P.club_challenge(3, monday + timedelta(weeks=w)) for w in range(len(P.CLUB))}
        self.assertEqual(seen, set(P.CLUB))  # every kind comes round
        self.assertEqual(P.club_target("c_games", 2), 15)  # a pair needs more than one day
        self.assertEqual(P.club_target("c_games", 100), 60)
        self.assertEqual(P.club_target("c_members", 1), 1)  # never more people than the club has
        for cid in P.CLUB:
            self.assertIn("{n}", P.CLUB[cid][0])


class ClubChallengeStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.db import Club

        self.db = Database("sqlite+aiosqlite:///:memory:")
        await self.db.init()
        self.ids = [(await self.db.create_user(f"C{i}_00", "x", "y")).id for i in range(3)]
        async with self.db.sessions() as s:
            club = Club(slug="c-1", name="C", about="", rules={}, created_by=self.ids[0])
            s.add(club)
            await s.commit()
            self.club = club.id

    async def test_claim_when_the_club_gets_there_and_only_if_you_helped(self):
        a, b, c = self.ids
        with unittest.mock.patch.object(P, "club_challenge", lambda cid, day: "c_members"):
            self.assertEqual(await self.db.claim_club_challenge(self.club, a, 3), "not_done")
            await self.db.log_activity([a, b], "club_game", self.club)
            await self.db.log_activity([a, b], "club_game", None)  # not in a club room: doesn't count
            info = await self.db.club_challenge(self.club, a, 3)
            self.assertEqual(
                (info["progress"], info["target"], info["title"]),
                (2, 2, "2 different members play a club game"),
            )
            self.assertEqual(await self.db.claim_club_challenge(self.club, c, 3), "not_helped")
            self.assertEqual(await self.db.claim_club_challenge(self.club, a, 3), "")
            self.assertEqual(await self.db.claim_club_challenge(self.club, a, 3), "claimed")  # once a week
            self.assertTrue((await self.db.club_challenge(self.club, a, 3))["claimed"])
        history = await self.db.coin_history(a)
        self.assertEqual(
            [e["delta"] for e in history["entries"] if e["reason"] == "club_challenge"], [P.CLUB_COINS]
        )

    async def test_two_members_cant_play_the_goal_in_alone(self):
        a, b, _ = self.ids
        with unittest.mock.patch.object(P, "club_challenge", lambda cid, day: "c_games"):
            for _ in range(40):  # a farming pair, all in one day
                await self.db.log_activity([a, b], "club_game", self.club)
            info = await self.db.club_challenge(self.club, a, 2)
            self.assertEqual(info["progress"], 2 * P.CLUB_DAY_GAMES)
            self.assertEqual(await self.db.claim_club_challenge(self.club, a, 2), "not_done")


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


class ActivityHookTests(unittest.IsolatedAsyncioTestCase):
    async def test_rooms_log_what_quests_count_and_skip_unfair_games(self):
        import asyncio

        from tests.test_accounts import Wallet
        from tests.test_ranked import room_of

        logged: list[tuple[list[int], str]] = []
        clubs: dict[str, int | None] = {}

        async def on_activity(ids, kind, club_id=None):
            logged.append((sorted(ids), kind))
            clubs[kind] = club_id

        hub, room, pids, conns = await room_of(2)
        hub.on_activity = on_activity
        wallet = Wallet({(1, "party_confetti"): 1})
        hub.spend_powerup, hub.refund_powerup = wallet.spend, wallet.refund
        await hub.handle_message(room, pids[0], conns[pids[0]], {"t": "party", "item": "party_confetti"})
        room.club_id = 9
        for quick in (True, False):
            await hub.handle_message(room, pids[0], conns[pids[0]], {"t": "start", "game": "four"})
            if not quick:
                room.game_began -= 120
            room.game.scores = lambda: {pids[0]: 300, pids[1]: 0}
            room.game.finished = True
            hub._maybe_finish(room)
            await asyncio.gather(*list(hub._tasks))
            room.phase = "lobby"
        kinds = [k for _, k in logged]
        self.assertEqual(kinds.count("party"), 1)
        self.assertEqual(kinds.count("host"), 1)  # the quick game logged nothing
        self.assertIn(([1, 2], "club_game"), logged)
        self.assertEqual(clubs["club_game"], 9)  # club challenges count it for that club
        self.assertIn(([1], "club_host"), logged)
