"""Fair play: every way of farming coins, prizes or rating is closed. Two friends replaying each other,
a ring of alts, a second account in another tab, a guest tab to beat, a thrown two-second game, signing
in mid-game, and brand-new accounts each get nothing extra."""

from __future__ import annotations

import asyncio
import unittest
import unittest.mock
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app import battles as B
from app import fairplay as F
from app import ratings as R
from app.config import Settings
from app.db import Database, RatingEvent, User
from app.main import create_app
from app.rooms import Hub
from tests.test_api import settings
from tests.test_rooms import Clock, FakeConn


def setUpModule():  # noqa: N802 - the unittest hook
    """Pin the week's featured battle format to one these tests never play (Battleships duels), so
    prizes are the usual ones whatever the date."""
    global _pin
    _pin = unittest.mock.patch.object(B, "format_of", lambda day: "fleet")
    _pin.start()


def tearDownModule():  # noqa: N802
    _pin.stop()


def finish(uid, coins, group, accounts=2, place=1):
    return {
        "user_id": uid,
        "game_id": "four",
        "place": place,
        "players": 2,
        "points": 300,
        "coins": coins,
        "group": group,
        "accounts": accounts,
    }


class RuleTests(unittest.TestCase):
    def test_the_pure_rules(self):
        self.assertEqual(F.group_key([3, 1, 2]), F.group_key([2, 3, 1, 1]))
        self.assertNotEqual(F.group_key([1, 2]), F.group_key([1, 3]))
        self.assertTrue(F.too_quick(F.MIN_GAME_SECONDS - 1))
        self.assertFalse(F.too_quick(F.MIN_GAME_SECONDS))
        self.assertEqual(F.solo_coins(50, 1), (F.SOLO_COINS, "solo"))
        self.assertEqual(F.solo_coins(50, 2), (50, ""))
        self.assertEqual(F.solo_coins(5, 1), (5, ""))


class StoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database("sqlite+aiosqlite:///:memory:")
        await self.db.init()
        self.ids = [(await self.db.create_user(f"P{i}_00", "x", "y")).id for i in range(5)]

    async def trust(self, ids):
        async with self.db.sessions() as s:
            old = datetime.now(UTC) - timedelta(days=F.NEW_ACCOUNT_DAYS + 1)
            await s.execute(update(User).where(User.id.in_(ids)).values(created_at=old, email_verified=True))
            await s.commit()

    async def test_two_friends_replaying_each_other_stop_earning(self):
        a, b, c, *_ = self.ids
        pair = F.group_key([a, b])
        for _ in range(F.REPEAT_LIMIT):
            paid = await self.db.record_results([finish(a, 50, pair), finish(b, 30, pair, place=2)], "s", 600)
            self.assertEqual((paid[a]["coins"], paid[a]["note"]), (50, ""))
        paid = await self.db.record_results([finish(a, 50, pair), finish(b, 30, pair, place=2)], "s", 600)
        self.assertEqual(
            paid, {a: {"coins": 0, "note": "repeat", "xp": 0}, b: {"coins": 0, "note": "repeat", "xp": 0}}
        )
        # playing someone new still pays
        other = F.group_key([a, c])
        paid = await self.db.record_results([finish(a, 50, other), finish(c, 30, other, place=2)], "s", 600)
        self.assertEqual(paid[a]["coins"], 50)

    async def test_accounts_on_one_device_never_earn_from_each_other(self):
        a, b, *_ = self.ids
        await self.db.note_device(a, "one-browser")
        await self.db.note_device(b, "one-browser")
        group = F.group_key([a, b])
        paid = await self.db.record_results([finish(a, 50, group), finish(b, 30, group, place=2)], "s", 600)
        self.assertEqual({p["note"] for p in paid.values()}, {"device"})
        self.assertIsNone(await self.db.rate_match("four", {a: 1, b: 2}))  # no rating either
        bid = await self.db.create_battle(None, "ABCD", "four", "duel", a, b)
        await self.trust([a, b])
        prizes = await self.db.settle_battle(bid, {a: 1, b: 2}, {a, b})
        self.assertEqual({p["note"] for p in prizes.values()}, {"device"})

    async def test_battles_new_accounts_quick_games_and_repeat_groups(self):
        a, b, c, d, e = self.ids
        bid = await self.db.create_battle(None, "ABCD", "four", "duel", a, b)
        prizes = await self.db.settle_battle(bid, {a: 1, b: 2}, {a, b})
        self.assertEqual({p["note"] for p in prizes.values()}, {"new"})  # brand-new, unconfirmed accounts
        await self.trust(self.ids)
        bid = await self.db.create_battle(None, "ABCD", "four", "duel", a, b)
        prizes = await self.db.settle_battle(bid, {a: 1, b: 2}, {a, b}, quick=True)
        self.assertEqual({p["note"] for p in prizes.values()}, {"quick"})
        # a ring of accounts can't farm group battles either
        ring = {c: 1, d: 2, e: 3}
        for _ in range(F.BATTLE_REPEAT_LIMIT):
            bid = await self.db.create_battle(None, "ABCD", "imposter", "group", c, None)
            self.assertEqual((await self.db.settle_battle(bid, ring, set(ring)))[c]["prize"], B.GROUP_PRIZE)
        bid = await self.db.create_battle(None, "ABCD", "imposter", "group", d, None)
        self.assertEqual(
            {p["note"] for p in (await self.db.settle_battle(bid, ring, set(ring))).values()}, {"repeat"}
        )


class RoomTests(unittest.IsolatedAsyncioTestCase):
    async def room(self, accounts, guests=0):
        paid = []

        async def pay(rows):
            paid.append(rows)
            return {r["user_id"]: {"coins": r["coins"], "note": r["note"]} for r in rows}

        hub = Hub(Settings(secret_key="s" * 40), clock=Clock(), intro_seconds=0, on_results=pay)
        hub.clock.t = 1000.0
        room, host, _ = hub.create_room("Host", user_id=accounts[0])
        conns = {host.id: FakeConn()}
        pids = [host.id]
        for i, uid in enumerate(accounts[1:]):
            _, p, _ = hub.join_room(room.code, f"P{i}", user_id=uid)
            pids.append(p.id)
        for i in range(guests):
            _, p, _ = hub.join_room(room.code, f"G{i}")
            pids.append(p.id)
        for pid in pids:
            conns.setdefault(pid, FakeConn())
            await hub.connect(room, pid, conns[pid])
        await hub.handle_message(room, host.id, conns[host.id], {"t": "start", "game": "four"})
        return hub, room, pids, paid

    async def end(self, hub, room, scores, after):
        hub.clock.t += after
        room.game.scores = lambda: scores
        room.game.finished = True
        hub._maybe_finish(room)
        await asyncio.gather(*list(hub._tasks))

    async def test_a_thrown_two_second_game_pays_nothing(self):
        hub, room, pids, paid = await self.room([1, 2])
        await self.end(hub, room, {pids[0]: 300, pids[1]: 0}, after=2)
        self.assertEqual({r["note"] for r in paid[0]}, {"quick"})
        self.assertEqual({n["coins"] for n in room.coin_news.values()}, {0})

    async def test_beating_your_own_guest_tab_pays_the_finisher_amount(self):
        hub, room, pids, paid = await self.room([1], guests=1)
        await self.end(hub, room, {pids[0]: 300, pids[1]: 0}, after=120)
        [row] = paid[0]
        self.assertEqual((row["coins"], row["note"]), (F.SOLO_COINS, "solo"))

    async def test_signing_in_mid_game_isnt_paid(self):
        hub, room, pids, paid = await self.room([1], guests=1)
        hub.link_account(room, pids[1], 2)  # the guest signs in after the game began
        await self.end(hub, room, {pids[0]: 0, pids[1]: 300}, after=120)
        self.assertEqual([r["user_id"] for r in paid[0]], [1])

    async def test_a_proper_game_pays_in_full(self):
        hub, room, pids, paid = await self.room([1, 2])
        await self.end(hub, room, {pids[0]: 300, pids[1]: 0}, after=120)
        self.assertEqual({r["user_id"]: (r["coins"], r["note"]) for r in paid[0]}, {1: (50, ""), 2: (30, "")})
        self.assertEqual({r["group"] for r in paid[0]}, {F.group_key([1, 2])})


class RatingRingTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_ring_of_accounts_stops_being_rated(self):
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.init()
        a, b, c, d = [(await db.create_user(f"R{i}_00", "x", "y")).id for i in range(4)]
        for _ in range(R.PAIR_LIMIT):
            self.assertIsNotNone(await db.rate_match("trivia", {a: 1, b: 2, c: 3}))
        self.assertIsNone(await db.rate_match("trivia", {c: 1, a: 2, b: 3}))
        self.assertIsNotNone(await db.rate_match("trivia", {a: 1, b: 2, c: 3, d: 4}))  # a new face counts


class WinTradingTests(unittest.IsolatedAsyncioTestCase):
    def test_the_rule(self):
        self.assertFalse(F.win_trading(F.WIN_TRADE_GAMES - 1, F.WIN_TRADE_GAMES - 1))  # too few to tell
        self.assertTrue(F.win_trading(F.WIN_TRADE_GAMES, F.WIN_TRADE_GAMES))
        self.assertFalse(F.win_trading(6, 10))  # a better player, not a pattern

    async def test_a_pair_that_always_goes_one_way_is_flagged(self):
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.init()
        a, b = [(await db.create_user(f"W{i}_00", "x", "y")).id for i in range(2)]
        flags = []
        for n in range(F.WIN_TRADE_GAMES):
            if n and n % R.PAIR_LIMIT == 0:  # the same pair only rates a few a day: a day goes by
                async with db.sessions() as s:
                    for row in (await s.execute(select(RatingEvent))).scalars():
                        row.at = row.at - timedelta(days=1)
                    await s.commit()
            self.assertIsNotNone(await db.rate_match("chess", {a: 2, b: 1}))
            flags.append(await db.win_trade({a: 2, b: 1}))
        self.assertEqual(flags[:-1], [None] * (F.WIN_TRADE_GAMES - 1))
        self.assertEqual(
            {k: flags[-1][k] for k in ("winner", "loser", "wins", "games")},
            {"winner": b, "loser": a, "wins": F.WIN_TRADE_GAMES, "games": F.WIN_TRADE_GAMES},
        )


def test_the_app_files_a_report_for_a_person_to_review(tmp_path):
    """A flag becomes a platform report from no one, for staff to look at; nothing is taken."""
    with TestClient(create_app(settings(tmp_path))) as client:
        db, hub = client.app.state.db, client.app.state.hub
        a, b = [client.portal.call(db.create_user, f"X{i}_00", "x", "y").id for i in range(2)]
        flag = {"winner": b, "loser": a, "winner_name": "X1_00", "loser_name": "X0_00", "wins": 8, "games": 8}
        with unittest.mock.patch.object(db, "win_trade", unittest.mock.AsyncMock(return_value=flag)):
            client.portal.call(hub.on_rated, "chess", {a: 2, b: 1})
        [report] = client.portal.call(db.staff_reports)
        assert (report.target_id, report.reporter_id, report.reason) == (b, None, "cheating")
        assert "win-trading" in report.note
