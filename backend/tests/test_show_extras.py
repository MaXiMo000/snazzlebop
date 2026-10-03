"""Show night extras: power cards, rivals, the audience's MVP and market seat, insider tips, dividends,
shorts through the hub, rematches and the season table."""

from __future__ import annotations

import json
import random
import unittest

from app import show as showlib
from app.games import REGISTRY, Player
from tests.test_rooms import FakeConn, HubHarness
from tests.test_show import finish


class CardAndRivalTests(unittest.TestCase):
    def test_apply_cards_double_then_shield_then_steal(self):
        plays = [
            {"pid": "a", "card": "double"},
            {"pid": "a", "card": "shield"},  # one card per player in real play; here both, to fix the order
            {"pid": "b", "card": "steal", "target": "c"},
        ]
        out, news = showlib.apply_cards(plays, {"a": -40, "b": 10, "c": 100})
        self.assertEqual(out, {"a": 0, "b": 10 + showlib.STEAL_POINTS, "c": 100 - showlib.STEAL_POINTS})
        self.assertEqual([n["effect"] for n in news], [-40, 80, showlib.STEAL_POINTS])

    def test_deal_cards_once_per_show(self):
        s = showlib.Show(playlist=["price", "telepathy"], jackpot=False)
        showlib.deal_cards(s, ["a", "b"], random.Random(1))
        self.assertEqual(set(s.cards), {"a", "b"})
        self.assertTrue(set(s.cards.values()) <= set(showlib.CARDS))
        s.plays.append({"pid": "a", "card": s.cards.pop("a"), "game": 0})
        showlib.deal_cards(s, ["a", "b", "c"], random.Random(1))
        self.assertNotIn("a", s.cards)  # played: no second card
        self.assertIn("c", s.cards)  # a latecomer gets one

    def test_rivals_pair_neighbours_on_the_board(self):
        pairs = showlib.rivals({"a": 500, "b": 10, "c": 480, "d": 0, "e": 7}, list("abcde"), random.Random(2))
        self.assertEqual(pairs, [("a", "c"), ("b", "e")])  # d (last) sits out
        news = showlib.settle_rivals(pairs, {"a": 5, "c": 9, "b": 3, "e": 3})
        self.assertEqual([n["winner"] for n in news], ["c", None])


class ShowExtrasHubTests(HubHarness):
    async def show(self, n=3, games=("price", "telepathy"), market=False):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, n)
        msg = {"t": "show", "games": list(games), "jackpot": False, "market": market}
        await hub.handle_message(room, host, conns[host], msg)
        return hub, room, host, conns

    async def test_cards_are_dealt_secret_and_revealed_at_the_results(self):
        hub, room, host, conns = await self.show()
        guest = next(p for p in room.players if p != host)
        room.show.cards[guest] = "double"
        await hub.broadcast(room)
        self.assertEqual(conns[guest].last["cards"]["you"]["card"], "double")
        self.assertNotIn(guest, json.dumps(conns[host].last["cards"]["you"]))  # only your own hand
        await hub.handle_message(room, guest, conns[guest], {"t": "card"})
        self.assertEqual(conns[host].last["cards"]["in_play"], 1)  # a card is down: not whose
        self.assertEqual(conns[host].last["cards"]["news"], [])
        await hub.handle_message(room, guest, conns[guest], {"t": "card"})
        self.assertIn("no_card", conns[guest].errors())  # one card a show
        room.game.round_scores[guest] = 120
        finish(hub, room)
        await hub.broadcast(room)
        news = conns[host].last["cards"]["news"]
        self.assertEqual([(n["pid"], n["card"], n["effect"]) for n in news], [(guest, "double", 120)])
        self.assertGreaterEqual(room.total_scores[guest], 240)  # doubled (plus any rival bonus)
        self.assertEqual(room.show.games[0]["scores"][guest] - room.total_scores[guest], 0)

    async def test_double_and_shield_only_early_steal_needs_a_rival(self):
        hub, room, host, conns = await self.show()
        guest = next(p for p in room.players if p != host)
        room.show.cards[guest] = "steal"
        await hub.handle_message(room, guest, conns[guest], {"t": "card", "target": guest})
        await hub.handle_message(room, guest, conns[guest], {"t": "card", "target": "ghost"})
        self.assertEqual(conns[guest].errors().count("bad_target"), 2)
        room.show.cards[host] = "shield"
        room.game.round = 2  # past the first round
        await hub.handle_message(room, host, conns[host], {"t": "card"})
        self.assertIn("too_late", conns[host].errors())
        self.assertEqual(room.show.cards[host], "shield")  # still in hand
        await hub.handle_message(room, guest, conns[guest], {"t": "card", "target": host})
        before = {p: room.game.round_scores[p] for p in room.players}
        finish(hub, room)
        steal = next(n for n in room.card_news if n["card"] == "steal")
        self.assertEqual((steal["pid"], steal["target"]), (guest, host))
        self.assertIsNotNone(before)

    async def test_peek_is_private(self):
        hub, room, host, conns = await self.show()
        guest = next(p for p in room.players if p != host)
        room.show.cards[guest] = "peek"
        await hub.handle_message(room, guest, conns[guest], {"t": "card"})
        seen = conns[guest].last["cards"]["you"]["peek"]
        self.assertIn("sealed spin", seen)  # Price Is Weird: which way the chaos spin goes
        self.assertIsNone(conns[host].last["cards"]["you"]["peek"])

    async def test_cards_not_in_one_off_games_or_for_the_audience(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "price"})
        await hub.handle_message(room, host, conns[host], {"t": "card"})
        self.assertIn("no_card", conns[host].errors())
        self.assertIsNone(conns[host].last["cards"])

    async def test_rivals_are_public_and_the_winner_gets_a_bonus(self):
        hub, room, host, conns = await self.show(n=4)
        pairs = conns[host].last["rivals"]["pairs"]
        self.assertEqual(len(pairs), 2)
        a, b = pairs[0]
        for p in room.players:
            room.game.round_scores[p] = 0
        room.game.round_scores[a] = 10
        finish(hub, room)
        self.assertEqual(room.total_scores[a] - room.game.scores()[a], showlib.RIVAL_BONUS)
        self.assertEqual(room.rival_news[0]["winner"], a)

    async def test_audience_votes_an_mvp_between_games(self):
        hub, room, host, conns = await self.show()
        _, fan, _ = hub.join_audience(room.code, "Fan")
        f = FakeConn()
        await hub.connect(room, fan.id, f)
        guest = next(p for p in room.players if p != host)
        await hub.handle_message(room, fan.id, f, {"t": "mvp", "target": guest})
        self.assertIn("mvp_closed", f.errors())  # only once the game is over
        finish(hub, room)
        await hub.handle_message(room, host, conns[host], {"t": "mvp", "target": guest})
        self.assertIn("audience_only", conns[host].errors())
        await hub.handle_message(room, fan.id, f, {"t": "mvp", "target": guest})
        self.assertEqual(f.last["crowd"]["mvp"]["you_voted"], guest)
        before = room.total_scores[guest]
        await hub.handle_message(room, host, conns[host], {"t": "next"})
        self.assertEqual(room.total_scores[guest] - before, 50)
        self.assertIn("Fan favourite", [r["title"] for r in room.show.reel])

    async def test_audience_trades_privately_and_one_player_gets_a_tip(self):
        hub, room, host, conns = await self.show(market=True)
        _, fan, _ = hub.join_audience(room.code, "Fan")
        f = FakeConn()
        await hub.connect(room, fan.id, f)
        self.assertEqual(f.last["market"]["you"]["cash"], showlib.START_CASH)
        await hub.handle_message(room, fan.id, f, {"t": "trade", "target": host, "qty": 3})
        await hub.handle_message(room, fan.id, f, {"t": "trade", "target": fan.id, "qty": 1})
        self.assertIn("bad_trade", f.errors())  # the audience isn't a stock
        self.assertEqual(f.last["market"]["you"]["holdings"], {host: 3})
        self.assertNotIn(fan.id, conns[host].last["market"]["prices"])
        tips = [c.last["market"]["you"]["tip"] for c in conns.values()]
        self.assertEqual(sum(1 for t in tips if t), 1)  # exactly one insider
        self.assertEqual(room.insider, next(p for p, c in conns.items() if c.last["market"]["you"]["tip"]))

    async def test_shorts_and_dividends_through_the_hub(self):
        hub, room, host, conns = await self.show(market=True)
        guest = next(p for p in room.players if p != host)
        await hub.handle_message(room, guest, conns[guest], {"t": "trade", "target": host, "qty": -5})
        await hub.handle_message(room, guest, conns[guest], {"t": "trade", "target": guest, "qty": -1})
        self.assertIn("bad_trade", conns[guest].errors())  # never short yourself
        await hub.handle_message(room, host, conns[host], {"t": "skip"})
        for p in room.players:
            room.game.round_scores[p] = 0
        room.game.round_scores[host] = 999
        cash = room.show.market.cash[guest]
        finish(hub, room)
        self.assertEqual(
            room.market_dividends[guest], -5 * showlib.DIVIDEND
        )  # the short pays the winner's dividend
        self.assertEqual(room.show.market.cash[guest], cash - 5 * showlib.DIVIDEND)

    async def test_rematch_keeps_the_lineup_and_the_season_counts(self):
        hub, room, host, conns = await self.show()
        guest = next(p for p in room.players if p != host)
        await hub.handle_message(room, host, conns[host], {"t": "rematch"})
        self.assertIn("no_show", conns[host].errors())  # not before the finale
        for _ in range(2):
            finish(hub, room)
            await hub.handle_message(room, host, conns[host], {"t": "next"})
        self.assertEqual(room.phase, "finale")
        season = conns[host].last["season"]
        self.assertEqual(season["number"], 1)
        self.assertEqual(sum(r["wins"] for r in season["table"].values()) >= 1, True)
        self.assertTrue(conns[host].last["show"]["can_rematch"])
        await hub.handle_message(room, guest, conns[guest], {"t": "rematch"})
        self.assertIn("not_host", conns[guest].errors())
        await hub.handle_message(room, host, conns[host], {"t": "rematch"})
        self.assertEqual((room.phase, room.game.game_id), ("game", "price"))
        self.assertEqual(room.show.playlist, ["price", "telepathy"])
        self.assertEqual(set(room.total_scores.values()), {0})  # a fresh show...
        self.assertEqual(room.season_no, 1)  # ...in the same season


class PeekHookTests(unittest.TestCase):
    """Every game's peek is either None or a short private string, and never crashes at the start."""

    def test_every_game(self):
        for gid, cls in REGISTRY.items():
            players = [Player(id=f"p{i}", name=f"N{i}") for i in range(max(cls.min_players, 4))]
            g = cls(players, rng=random.Random(5))
            g.start()
            for p in g.player_ids:
                out = g.peek(p)
                self.assertTrue(out is None or (isinstance(out, str) and 0 < len(out) < 160), (gid, out))

    def test_secret_role_peeks_never_name_the_secret(self):
        from app.games.alibi import Alibi
        from app.games.mural import MoleInTheMural

        for seed in range(20):
            g = Alibi([Player(id=f"p{i}", name=f"N{i}") for i in range(5)], rng=random.Random(seed))
            g.start()
            self.assertNotIn(g.name_of(g.killer), g.peek("p0") if g.killer != "p0" else "")
            m = MoleInTheMural([Player(id=f"p{i}", name=f"N{i}") for i in range(5)], rng=random.Random(seed))
            m.start()
            for mole in m.moles:
                self.assertNotIn(f"{m.name_of(mole)} is", m.peek("p0") or "")


if __name__ == "__main__":
    unittest.main()
