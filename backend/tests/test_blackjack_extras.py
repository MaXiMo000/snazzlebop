"""Blackjack extras: solo, side bets, the Chaos card and tournament knockouts (rigged shoes, exact chips)."""

from __future__ import annotations

import random
import unittest

from app.games import GameError, Player
from app.games.blackjack import CHAOS, START_CHIPS, BlackjackShowdown

SPECTATORS = ("tv:screen", "au:fan")


def table(n: int, seed: int = 1, **options: str) -> BlackjackShowdown:
    g = BlackjackShowdown(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)], rng=random.Random(seed), options=options or None
    )
    g.start()
    g.chaos_hand = 99  # no chaos unless a test asks for it
    return g


def rig(g: BlackjackShowdown, *cards: str) -> None:
    """Next cards off the shoe, in dealing order (the shoe pops from the end)."""
    g.shoe = list(reversed(cards))


class SoloTests(unittest.TestCase):
    def test_one_player_against_the_dealer(self):
        g = table(1)
        self.assertEqual(g.view_for("p0")["side_sizes"], [])
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "bet", "amount": 50, "side_on": "p0", "side_amount": 50})
        # p0: 10 + 9 = 19; dealer: 10 + 7 = 17, stands. Deal order: p0, dealer, p0, dealer.
        rig(g, "10S", "10H", "9S", "7H")
        g.handle("p0", {"a": "bet", "amount": 100})
        g.handle("p0", {"a": "stand"})
        self.assertEqual(g.result["net"], {"p0": 100})
        self.assertEqual(g.chips["p0"], START_CHIPS + 100)


class SideBetTests(unittest.TestCase):
    def deal(self, g, cards, bets):
        rig(g, *cards)
        for pid, msg in bets.items():
            g.handle(pid, {"a": "bet", **msg})

    def test_backing_a_winner_pays_one_to_one_and_chips_add_up(self):
        g = table(3)
        before = sum(g.chips.values())
        # deal order per round: p0, p1, p2, dealer. p0 20, p1 15, p2 17; dealer 18 (stands).
        cards = ["10S", "10H", "10D", "10C", "10S", "5H", "7D", "8C"]
        self.deal(
            g,
            cards,
            {
                "p0": {"amount": 100},
                "p1": {"amount": 50, "side_on": "p0", "side_amount": 100},  # backs the winner
                "p2": {"amount": 50, "side_on": "p1", "side_amount": 50},  # backs a loser
            },
        )
        self.assertEqual(
            g.view_for("tv:x")["side"], {"p1": {"on": "p0", "amount": 100}, "p2": {"on": "p1", "amount": 50}}
        )
        for pid in ("p0", "p1", "p2"):
            g.handle(pid, {"a": "stand"})
        r = g.result
        self.assertEqual(r["side"]["p1"]["pay"], 200)
        self.assertEqual(r["side"]["p2"]["pay"], 0)
        self.assertEqual(r["net"], {"p0": 100, "p1": -50 + 100, "p2": -50 - 50})
        # The house pays out and takes in exactly what the nets say.
        self.assertEqual(sum(g.chips.values()) - before, sum(r["net"].values()))

    def test_a_push_refunds_the_side_bet(self):
        g = table(2)
        # p0 18, p1 15; dealer 18. Order: p0, p1, dealer, p0, p1, dealer.
        self.deal(
            g,
            ["10S", "10H", "10D", "8S", "5H", "8D"],
            {"p0": {"amount": 50}, "p1": {"amount": 50, "side_on": "p0", "side_amount": 50}},
        )
        g.handle("p0", {"a": "stand"})
        g.handle("p1", {"a": "stand"})
        self.assertEqual(g.result["side"]["p1"]["pay"], 50)

    def test_side_bet_validation(self):
        g = table(3)
        g.chips["p2"] = 120
        for bad in (
            {"amount": 50, "side_on": "p0", "side_amount": 50},  # yourself (p0 bets)
            {"amount": 50, "side_on": "nobody", "side_amount": 50},
            {"amount": 50, "side_on": "p1", "side_amount": 75},
            {"amount": 50, "side_on": "p1", "side_amount": True},
            {"amount": 50, "side_on": 7, "side_amount": 50},
        ):
            with self.assertRaises(GameError, msg=bad):
                g.handle("p0", {"a": "bet", **bad})
        with self.assertRaises(GameError):  # 100 + 50 > 120 chips
            g.handle("p2", {"a": "bet", "amount": 100, "side_on": "p0", "side_amount": 50})
        self.assertEqual(g.bets, {})  # nothing half-placed
        self.assertEqual(g.chips["p2"], 120)


class ChaosTests(unittest.TestCase):
    def test_the_chaos_card_is_secret_until_its_hand(self):
        g = BlackjackShowdown([Player(id=f"p{i}", name=f"N{i}") for i in range(2)], rng=random.Random(7))
        g.start()
        self.assertGreaterEqual(g.chaos_hand, 1)  # never the first hand
        for viewer in ("p0", *SPECTATORS):
            view = g.view_for(viewer)
            self.assertIsNone(view["chaos"])
            self.assertTrue(view["chaos_coming"])
            self.assertNotIn(g.chaos_event, str(view))
        g.round = g.chaos_hand
        self.assertEqual(g.view_for("tv:x")["chaos"]["id"], g.chaos_event)

    def chaos(self, event, cards, act="stand"):
        g = table(1)
        g.chaos_hand, g.chaos_event = 0, event
        rig(g, *cards)
        g.handle("p0", {"a": "bet", "amount": 100})
        if g.phase == "play":
            g.handle("p0", {"a": act})
        return g

    def test_double_payouts(self):
        g = self.chaos("double_pay", ["10S", "10H", "9S", "8H"])  # 19 vs 18
        self.assertEqual(g.result["net"], {"p0": 200})
        g = self.chaos("double_pay", ["AS", "10H", "KS", "8H"])  # blackjack: 3:2 doubled
        self.assertEqual(g.result["net"], {"p0": 300})

    def test_ties_pay(self):
        g = self.chaos("push_pays", ["10S", "10H", "8S", "8H"])  # 18 vs 18
        self.assertEqual(g.result["outcomes"]["p0"], ["push"])
        self.assertEqual(g.result["net"], {"p0": 100})

    def test_dealer_hits_soft_17(self):
        # p0 stands on 18; dealer A + 6 = soft 17, hits a 3 -> 20 and wins.
        g = self.chaos("soft17", ["10S", "AH", "8S", "6H", "3C"])
        self.assertEqual(g.result["dealer_value"], 20)
        self.assertEqual(g.result["net"], {"p0": -100})
        # Without the card the dealer stands on soft 17 and p0's 18 wins.
        g = table(1)
        rig(g, "10S", "AH", "8S", "6H", "3C")
        g.handle("p0", {"a": "bet", "amount": 100})
        g.handle("p0", {"a": "stand"})
        self.assertEqual(g.result["dealer_value"], 17)
        self.assertEqual(set(CHAOS), {"soft17", "double_pay", "push_pays"})


class TournamentTests(unittest.TestCase):
    def test_needs_three_players(self):
        with self.assertRaises(GameError):
            table(2, mode="tournament")

    def test_shortest_stack_goes_out_from_hand_two_and_the_last_one_standing_wins(self):
        g = table(3, mode="tournament")
        self.assertEqual(g.hands_total, 5)
        while not g.finished:
            if g.phase == "bet":
                for pid in list(g.active):
                    if pid not in g.bets and g.phase == "bet":
                        # p2 bets big and (with the house edge) usually drops lowest first
                        g.handle(
                            pid, {"a": "bet", "amount": 500 if pid == "p2" and g.chips[pid] >= 500 else 50}
                        )
            else:
                g.advance()
        self.assertTrue(g.finished)
        # Everyone is placed exactly once, and points follow the placings.
        self.assertEqual(sorted(g.standings), ["p0", "p1", "p2"])
        scores = g.scores()
        self.assertEqual([scores[p] for p in g.standings][1:], [100, 0])
        self.assertIn(scores[g.standings[0]], (200, 200 + 300))
        knocked = [o["player"] for o in g.out]
        self.assertEqual(len(knocked), len(set(knocked)))

    def test_knocked_out_players_cannot_bet(self):
        g = table(3, mode="tournament")
        g.active = ["p0", "p1"]
        with self.assertRaises(GameError):
            g.handle("p2", {"a": "bet", "amount": 50})

    def test_a_tie_for_shortest_stack_spares_everyone(self):
        g = table(3, mode="tournament")
        g.round = 1
        g.chips = {"p0": 700, "p1": 700, "p2": 900}
        self.assertEqual(g._knockouts(), [])
        g.chips = {"p0": 700, "p1": 40, "p2": 900}  # busted p1 goes; then p0 is the single lowest
        self.assertEqual(g._knockouts(), ["p1", "p0"])
        self.assertEqual(g.active, ["p2"])


class OptionsTests(unittest.TestCase):
    def test_hub_validates_options(self):
        from app.games import REGISTRY
        from app.rooms import Hub, HubError

        cls = REGISTRY["blackjack"]
        self.assertEqual(Hub._options(cls, None), {})
        self.assertEqual(Hub._options(cls, {"mode": "tournament"}), {"mode": "tournament"})
        for bad in ({"mode": "chaos"}, {"turbo": "yes"}, "tournament", {"mode": "classic", "x": "y"}):
            with self.assertRaises(HubError, msg=repr(bad)):
                Hub._options(cls, bad)
        with self.assertRaises(HubError):
            Hub._options(REGISTRY["frenemy"], {"mode": "classic"})


if __name__ == "__main__":
    unittest.main()
