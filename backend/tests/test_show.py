"""Show night, the jackpot finale, the audience, live reactions and the host's one-liners."""

from __future__ import annotations

import random
import unittest

from app import show as showlib
from app.games import GameError, Player
from app.games.base import Deck
from app.games.jackpot import FLOOR, Jackpot
from app.rooms import MAX_AUDIENCE, REACT_GAP, ROOM_REACTS_PER_SEC, HubError
from tests.test_rooms import FakeConn, HubHarness


def finish(hub, room) -> None:
    """End the running game at once (host skips until it's over)."""
    for _ in range(60):
        if room.phase != "game":
            return
        room.game.advance()
        hub._maybe_finish(room)
    raise AssertionError("game did not finish")


class JackpotTests(unittest.TestCase):
    def make(self, stakes, seed=4):
        players = [Player(id=f"p{i}", name=f"N{i}") for i in range(len(stakes))]
        game = Jackpot(
            players, rng=random.Random(seed), stakes=dict(zip([p.id for p in players], stakes, strict=True))
        )
        game.start()
        return game

    def test_right_call_wins_the_stake_wrong_loses_it_and_silence_costs_nothing(self):
        game = self.make([1000, 50, 300])
        wrong = "lower" if game.answer == "higher" else "higher"
        game.handle("p0", {"a": "wager", "amount": 600, "call": game.answer})
        game.handle("p1", {"a": "wager", "amount": FLOOR, "call": wrong})  # under the floor: still 200
        game.advance()
        self.assertTrue(game.finished)
        self.assertEqual(game.scores(), {"p0": 600, "p1": -FLOOR, "p2": 0})

    def test_tag_is_never_the_price_and_answer_matches(self):
        for seed in range(300):
            game = self.make([0, 0], seed)
            self.assertNotEqual(game.tag, game.item["price"])
            self.assertEqual(game.answer, "higher" if game.item["price"] > game.tag else "lower")

    def test_wagers_are_secret_until_the_reveal(self):
        game = self.make([500, 500, 500])
        game.handle("p0", {"a": "wager", "amount": 123, "call": "higher"})
        for viewer in ("p1", "tv:x", "au:y"):
            view = game.view_for(viewer)
            self.assertEqual(view["locked"], ["p0"])
            self.assertIsNone(view["you"])
            self.assertIsNone(view["result"])
            self.assertNotIn("123", str(view))
        self.assertEqual(game.view_for("p0")["you"], {"amount": 123, "call": "higher"})

    def test_input_validation(self):
        game = self.make([500, 0])
        for bad in (
            {"a": "wager", "amount": 501, "call": "higher"},
            {"a": "wager", "amount": -1, "call": "higher"},
            {"a": "wager", "amount": True, "call": "higher"},
            {"a": "wager", "amount": 10, "call": "sideways"},
            {"a": "bet", "amount": 10, "call": "higher"},
        ):
            with self.assertRaises(GameError, msg=bad):
                game.handle("p0", bad)
        with self.assertRaises(GameError):
            game.handle("intruder", {"a": "wager", "amount": 1, "call": "higher"})


class QuipTests(unittest.TestCase):
    def test_fill_only_replaces_known_placeholders(self):
        self.assertEqual(showlib.fill("{winner} {nope} {0}", {"winner": "Ana"}), "Ana {nope} {0}")

    def test_mood_and_placeholders_fit_the_result(self):
        names = {"a": "Ana", "b": "Bo", "c": "Cy"}
        decks: dict[str, Deck] = {}
        rng = random.Random(1)
        solo = showlib.quip({"a": 50}, names, "Blackjack", decks, rng)
        self.assertIn("Ana", solo)
        self.assertNotIn("{", solo)
        for scores in (
            {"a": 500, "b": 495, "c": 10},
            {"a": 900, "b": 100, "c": 0},
            {"a": 300, "b": 300, "c": 1},
        ):
            line = showlib.quip(scores, names, "Alibi", decks, rng)
            self.assertTrue(line)
            self.assertNotIn("{", line)

    def test_a_shared_crown_at_the_finale(self):
        names = {"a": "Ana", "b": "Bo", "c": "Cy"}
        line = showlib.quip({"a": 5, "b": 5, "c": 1}, names, "the show", {}, random.Random(1), "show")
        self.assertEqual(line, "We can't split them: Ana and Bo share tonight's crown!")

    def test_everyone_level_is_a_dead_heat_not_a_two_way_tie(self):
        names = {"a": "Ana", "b": "Bo", "c": "Cy"}
        line = showlib.quip({"a": 0, "b": 0, "c": 0}, names, "Alibi", {}, random.Random(1))
        self.assertEqual(line, "A dead heat on Alibi: everyone finished on 0.")

    def test_no_repeats_within_a_mood_until_the_deck_runs_out(self):
        decks: dict[str, Deck] = {}
        rng = random.Random(2)
        lines = [showlib.quip({"a": 900, "b": 100}, {"a": "A", "b": "B"}, "G", decks, rng) for _ in range(6)]
        self.assertEqual(len(set(lines)), 6)


class ShowHubTests(HubHarness):
    async def test_a_full_show_with_jackpot_and_finale(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        room.total_scores = {pid: 77 for pid in room.players}  # earlier games: a show starts fresh
        await hub.handle_message(room, host, conns[host], {"t": "show", "games": ["price", "telepathy"]})
        self.assertEqual(room.phase, "game")
        self.assertEqual(room.game.game_id, "price")
        self.assertEqual(set(room.total_scores.values()), {0})
        finish(hub, room)
        state = conns[host].last if conns[host].sent else None
        await hub.broadcast(room)
        state = conns[host].last
        self.assertEqual(state["room"]["phase"], "results")
        self.assertEqual(state["show"]["next"], "telepathy")
        self.assertTrue(state["quip"])
        await hub.handle_message(room, host, conns[host], {"t": "next"})
        self.assertEqual(room.game.game_id, "telepathy")
        finish(hub, room)
        await hub.handle_message(room, host, conns[host], {"t": "next"})
        self.assertEqual(room.game.game_id, "jackpot")
        stakes = room.game.stakes
        self.assertEqual(stakes, {pid: room.total_scores[pid] for pid in room.players})
        finish(hub, room)
        await hub.handle_message(room, host, conns[host], {"t": "next"})
        self.assertEqual(room.phase, "finale")
        state = conns[host].last
        self.assertTrue(state["show"]["finished"])
        self.assertEqual([g["game"] for g in state["show"]["games"]], ["price", "telepathy", "jackpot"])
        self.assertEqual(state["show"]["awards"][0]["icon"], "👑")  # champion(s) first
        self.assertTrue(state["quip"])
        await hub.handle_message(room, host, conns[host], {"t": "next"})  # nothing left
        self.assertIn("no_show", conns[host].errors())
        await hub.handle_message(room, host, conns[host], {"t": "lobby"})
        self.assertIsNone(room.show)

    async def test_show_validation_and_host_only(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        guest = next(p for p in room.players if p != host)
        for bad in (
            ["price"],
            ["price", "price"],
            ["price", "nope"],
            "price",
            ["a", "b", "c", "d", "e", "f", "g"],
        ):
            await hub.handle_message(room, host, conns[host], {"t": "show", "games": bad})
        self.assertEqual(conns[host].errors().count("bad_show"), 5)
        await hub.handle_message(
            room, host, conns[host], {"t": "show", "games": ["price", "alibi"], "jackpot": "yes"}
        )
        await hub.handle_message(room, guest, conns[guest], {"t": "show", "games": ["price", "alibi"]})
        self.assertIn("not_host", conns[guest].errors())
        # Not enough players for the opener: nothing changes.
        await hub.handle_message(room, host, conns[host], {"t": "show", "games": ["alibi", "price"]})
        self.assertIsNone(room.show)
        self.assertEqual(room.phase, "lobby")

    async def test_skip_a_segment_the_room_cant_play(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        await hub.handle_message(
            room, host, conns[host], {"t": "show", "games": ["price", "alibi", "telepathy"], "jackpot": False}
        )
        finish(hub, room)
        await hub.handle_message(room, host, conns[host], {"t": "next"})  # Alibi needs 4
        self.assertIn("bad_player_count", conns[host].errors())
        self.assertEqual(room.phase, "results")
        await hub.handle_message(room, host, conns[host], {"t": "next", "skip": True})
        self.assertEqual(room.game.game_id, "telepathy")
        finish(hub, room)
        await hub.handle_message(room, host, conns[host], {"t": "next"})
        self.assertEqual(room.phase, "finale")  # no jackpot this time

    async def test_theme_host_only_and_validated(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        guest = next(p for p in room.players if p != host)
        await hub.handle_message(room, guest, conns[guest], {"t": "theme", "theme": "movies"})
        await hub.handle_message(room, host, conns[host], {"t": "theme", "theme": "nope"})
        self.assertEqual(room.theme, "")
        await hub.handle_message(room, host, conns[host], {"t": "theme", "theme": "spooky"})
        self.assertEqual(conns[guest].last["room"]["theme"], "spooky")
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "price"})
        self.assertEqual(room.game.theme, "spooky")


class AudienceTests(HubHarness):
    async def test_audience_joins_full_or_running_rooms_but_not_locked_ones(self):
        hub = self.make_hub(max_players_per_room=3)
        room, host, conns = await self.party(hub, 3)
        with self.assertRaises(HubError):
            hub.join_room(room.code, "Late")
        _, watcher, token = hub.join_audience(room.code, "Late")
        self.assertTrue(watcher.id.startswith("au:"))
        self.assertTrue(hub.is_member(room, watcher.id))
        with self.assertRaises(HubError):
            hub.join_audience(room.code, "late")  # names are unique across seats and crowd
        with self.assertRaises(HubError):
            hub.join_audience(room.code, "Host")
        room.locked = True
        with self.assertRaises(HubError):
            hub.join_audience(room.code, "Other")
        room.locked = False
        for i in range(MAX_AUDIENCE - 1):
            hub.join_audience(room.code, f"Fan{i}")
        with self.assertRaises(HubError):
            hub.join_audience(room.code, "OneTooMany")

    async def test_audience_can_only_react_and_predict(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        _, w, _ = hub.join_audience(room.code, "Fan")
        fan = FakeConn()
        await hub.connect(room, w.id, fan)
        self.assertEqual(fan.last["role"], "audience")
        self.assertEqual(conns[host].last["crowd"]["members"][0]["name"], "Fan")
        for msg in (
            {"t": "start", "game": "price"},
            {"t": "act", "a": "x"},
            {"t": "skip"},
            {"t": "kick", "target": host},
        ):
            await hub.handle_message(room, w.id, fan, msg)
        self.assertEqual(fan.errors().count("audience_only"), 4)
        self.assertEqual(room.phase, "lobby")

    async def test_predictions_score_for_backing_the_winner_and_stay_anonymous(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        _, w1, _ = hub.join_audience(room.code, "Fan1")
        _, w2, _ = hub.join_audience(room.code, "Fan2")
        f1, f2 = FakeConn(), FakeConn()
        await hub.connect(room, w1.id, f1)
        await hub.connect(room, w2.id, f2)
        await hub.handle_message(room, w1.id, f1, {"t": "predict", "target": host})
        self.assertIn("predict_closed", f1.errors())  # no game yet
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "price"})
        guest = next(p for p in room.players if p != host)
        await hub.handle_message(room, w1.id, f1, {"t": "predict", "target": host})
        await hub.handle_message(room, w2.id, f2, {"t": "predict", "target": guest})
        await hub.handle_message(room, w2.id, f2, {"t": "predict", "target": "nobody"})
        self.assertIn("bad_target", f2.errors())
        await hub.handle_message(room, host, conns[host], {"t": "predict", "target": host})
        self.assertIn("audience_only", conns[host].errors())
        crowd = conns[guest].last["crowd"]
        self.assertEqual({c["id"] for c in crowd["contestants"]}, set(room.game.player_ids))
        self.assertEqual(crowd["picks"], {host: 1, guest: 1})
        self.assertNotIn(w1.id, str(crowd["picks"]))
        self.assertIsNone(crowd["you_picked"])
        self.assertEqual(f1.last["crowd"]["you_picked"], host)
        room.game.round_scores[host] = 999  # make the host the clear winner
        room.game.finished = True
        hub._maybe_finish(room)
        self.assertEqual((w1.points, w2.points), (1, 0))

    async def test_host_can_remove_audience_members_any_time(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        _, w, _ = hub.join_audience(room.code, "Heckler")
        fan = FakeConn()
        await hub.connect(room, w.id, fan)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "price"})
        await hub.handle_message(room, host, conns[host], {"t": "kick", "target": w.id})
        await __import__("asyncio").sleep(0)
        self.assertNotIn(w.id, room.audience)
        self.assertEqual(fan.closed, 4001)
        self.assertFalse(hub.is_member(room, w.id))


class ReactionTests(HubHarness):
    async def test_reactions_are_whitelisted_and_throttled(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        await hub.handle_message(room, host, conns[host], {"t": "react", "e": "<img>"})
        self.assertIn("bad_reaction", conns[host].errors())
        await hub.handle_message(room, host, conns[host], {"t": "react", "e": "🔥"})
        await hub.handle_message(room, host, conns[host], {"t": "react", "e": "😂"})  # too soon: ignored
        self.assertEqual([r["e"] for r in room.reactions], ["🔥"])
        self.clock.t += REACT_GAP
        await hub.handle_message(room, host, conns[host], {"t": "react", "e": "😂"})
        self.assertEqual([r["e"] for r in room.reactions], ["🔥", "😂"])
        self.assertEqual(conns[host].last["reactions"][-1]["by"], "Host")

    async def test_room_wide_ceiling(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        ids = []
        for i in range(ROOM_REACTS_PER_SEC + 3):
            _, w, _ = hub.join_audience(room.code, f"Fan{i}")
            ids.append(w.id)
        for wid in ids:
            await hub.handle_message(room, wid, FakeConn(), {"t": "react", "e": "👏"})
        self.assertEqual(len(room.reactions), ROOM_REACTS_PER_SEC)
        self.clock.t += 1.0
        await hub.handle_message(room, ids[-1], FakeConn(), {"t": "react", "e": "👏"})
        self.assertEqual(len(room.reactions), ROOM_REACTS_PER_SEC + 1)

    async def test_tv_cannot_react(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        room, token = hub.issue_tv(room.code)
        tv_id = next(iter(room.viewers))
        tv = FakeConn()
        await hub.handle_message(room, tv_id, tv, {"t": "react", "e": "🔥"})
        self.assertIn("read_only", tv.errors())
        self.assertEqual(room.reactions, [])


if __name__ == "__main__":
    unittest.main()


class AwardTests(unittest.TestCase):
    def test_draws_crown_nobody_and_steady_hand_means_near_the_top(self):
        names = {"a": "Ana", "b": "Bo", "c": "Cy", "d": "Di"}
        s = showlib.Show(playlist=["price", "telepathy"], jackpot=True)
        s.games = [
            {"game": "price", "title": "P", "scores": {"a": 0, "b": 0, "c": 0, "d": 0}},
            {"game": "telepathy", "title": "T", "scores": {"a": 0, "b": 0, "c": 0, "d": 0}},
            {"game": "jackpot", "title": "J", "scores": {"a": -200, "b": 0, "c": 0, "d": 0}},
        ]
        titles = [a["title"] for a in showlib.awards(s, {"a": -200, "b": 0, "c": 0, "d": 0}, names)]
        self.assertEqual(titles, ["Joint champions"])

    def test_segment_king_and_steady_hand(self):
        names = {"a": "Ana", "b": "Bo", "c": "Cy", "d": "Di"}
        s = showlib.Show(playlist=["price", "telepathy", "mural"], jackpot=False)
        s.games = [
            {"game": "price", "title": "P", "scores": {"a": 900, "b": 300, "c": 200, "d": 0}},
            {"game": "telepathy", "title": "T", "scores": {"a": 500, "b": 400, "c": 0, "d": 100}},
            {"game": "mural", "title": "M", "scores": {"a": 0, "b": 300, "c": 400, "d": 100}},
        ]
        awards = showlib.awards(s, {"a": 1400, "b": 1000, "c": 600, "d": 200}, names)
        self.assertEqual(awards[0]["text"], "Ana with 1400 points")
        self.assertEqual(
            awards[1], {"icon": "🏆", "title": "Segment king", "text": "Ana won 2 games tonight"}
        )
        self.assertEqual(awards[2]["title"], "Steady hand")
        self.assertIn("Bo", awards[2]["text"])


class MarketTests(unittest.TestCase):
    def market(self, *pids):
        m = showlib.Market()
        for p in pids:
            m.seat(p)
        return m

    def test_buying_selling_and_limits(self):
        m = self.market("a", "b")
        m.trade("a", "b", 5)
        self.assertEqual((m.cash["a"], m.holdings["a"]), (500, {"b": 5}))
        m.trade("a", "b", -2)
        self.assertEqual((m.cash["a"], m.holdings["a"]), (700, {"b": 3}))
        for bad in (0, 11):  # nothing, too many at once
            with self.assertRaises(ValueError, msg=bad):
                m.trade("a", "b", bad)
        m.trade("a", "a", 7)  # backing yourself is allowed
        with self.assertRaises(ValueError):
            m.trade("a", "b", 1)  # $0 left
        m.cash["a"] = 10_000
        for _ in range(1):
            m.trade("a", "b", 10)
        with self.assertRaises(ValueError):
            m.trade("a", "b", 10)  # 3 + 10 + 10 > 20 shares of one player
        with self.assertRaises(ValueError):
            m.trade("a", "ghost", 1)

    def test_shorts_dividends_and_tips(self):
        m = self.market("a", "b", "c")
        m.trade("a", "b", -5)  # a short: cash now, owe the price later
        self.assertEqual((m.cash["a"], m.holdings["a"]), (1500, {"b": -5}))
        with self.assertRaises(ValueError):
            m.trade("a", "a", -1)  # never short yourself
        for _ in range(1):
            m.trade("a", "b", -10)
        with self.assertRaises(ValueError):
            m.trade("a", "b", -10)  # past the 20-share short limit
        m.reprice({"b": 0, "a": 5, "c": 9})  # b came last: -20%
        self.assertEqual(m.worth("a"), m.cash["a"] - 15 * 80)
        m.trade("c", "b", 2)
        paid = m.pay_dividends(["b"])
        self.assertEqual(paid, {"a": -15 * showlib.DIVIDEND, "c": 2 * showlib.DIVIDEND})
        m.seat("au:x", listed=False)  # the audience trades but isn't a stock
        self.assertNotIn("au:x", m.prices)
        tip = m.tip("b", random.Random(1), {"a": "Ann", "c": "Cy", "b": "Bo"})
        self.assertTrue(tip.startswith(("Ann holds -15 × Bo", "Cy holds +2 × Bo")), tip)

    def test_prices_follow_placement_with_ties_and_a_floor(self):
        m = self.market("a", "b", "c")
        moves = m.reprice({"a": 500, "b": 100, "c": 0})
        self.assertEqual(m.prices, {"a": 130, "b": 105, "c": 80})
        self.assertEqual(moves["b"], 0.05)
        m.reprice({"a": 50, "b": 50, "c": 0})  # a and b share 1st/2nd: the average move
        self.assertEqual(m.prices["a"], round(130 * 1.175))
        m.prices["c"] = 11
        m.reprice({"a": 9, "b": 5, "c": 0})
        self.assertEqual(m.prices["c"], showlib.MIN_PRICE)

    def test_worth_and_bonus(self):
        m = self.market("a", "b")
        m.trade("a", "b", 5)
        m.reprice({"b": 10, "a": 0})  # b's price 100 -> 130
        self.assertEqual(m.worth("a"), 500 + 5 * 130)
        self.assertEqual(m.bonus("a"), 15)  # +$150 -> 15 points
        self.assertEqual(m.bonus("b"), 0)


class MarketHubTests(HubHarness):
    async def test_a_show_with_the_stock_exchange(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        guest = next(p for p in room.players if p != host)
        await hub.handle_message(
            room,
            host,
            conns[host],
            {"t": "show", "games": ["price", "telepathy"], "jackpot": False, "market": True},
        )
        self.assertEqual(room.phase, "market")
        self.assertIsNone(room.game)
        view = conns[guest].last["market"]
        self.assertTrue(view["open"])
        self.assertEqual(view["you"]["cash"], showlib.START_CASH)
        await hub.handle_message(room, guest, conns[guest], {"t": "trade", "target": host, "qty": 4})
        await hub.handle_message(room, guest, conns[guest], {"t": "trade", "target": host, "qty": True})
        self.assertIn("bad_trade", conns[guest].errors())
        # Books are private until the finale; prices and the trade count are public.
        self.assertEqual(conns[guest].last["market"]["you"]["holdings"], {host: 4})
        self.assertEqual(conns[host].last["market"]["you"]["holdings"], {})
        self.assertEqual(conns[host].last["market"]["books"], {})
        self.assertEqual(conns[host].last["market"]["trades"], 1)
        await hub.handle_message(room, guest, conns[guest], {"t": "skip"})  # only the host rings the bell
        self.assertEqual(room.phase, "market")
        await hub.handle_message(room, host, conns[host], {"t": "skip"})
        self.assertEqual((room.phase, room.game.game_id), ("game", "price"))
        await hub.handle_message(room, guest, conns[guest], {"t": "trade", "target": host, "qty": 1})
        self.assertIn("market_closed", conns[guest].errors())
        room.game.round_scores[host] = 999
        finish(hub, room)
        self.assertEqual(room.show.market.prices[host], 130)  # won the segment: +30%
        await hub.handle_message(room, host, conns[host], {"t": "next"})
        self.assertEqual(room.phase, "market")  # trading again before Telepathy
        self.clock.t += 31
        await hub.tick()  # the bell rings on time without the host
        self.assertEqual(room.game.game_id, "telepathy")
        finish(hub, room)
        before = dict(room.total_scores)
        await hub.handle_message(room, host, conns[host], {"t": "next"})
        self.assertEqual(room.phase, "finale")
        m = room.show.market
        self.assertEqual(room.total_scores[guest] - before[guest], m.bonus(guest))
        fin = conns[host].last["market"]
        self.assertEqual(fin["books"][guest], {host: 4})
        self.assertEqual(fin["worth"][guest], m.worth(guest))
        richest = max(m.cash, key=m.worth)
        has_award = "Market tycoon" in [a["title"] for a in room.show.awards]
        self.assertEqual(has_award, m.worth(richest) > showlib.START_CASH)
