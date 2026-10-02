"""Blackjack Showdown: hand values, dealer rules, payouts, splits, turn order, timers and secrecy."""

from __future__ import annotations

import random
import unittest

from app.games import GameError, Player
from app.games.blackjack import BlackjackShowdown, hand_value

TV = "tv:screen"


def make(n=3, seed=1):
    clock = [1000.0]
    players = [Player(id=f"p{i}", name=f"N{i}") for i in range(n)]
    g = BlackjackShowdown(players, rng=random.Random(seed), clock=lambda: clock[0])
    g.start()
    return g, [p.id for p in players], clock


def rig(g, cards):
    """Put these cards on top of the shoe (next dealt first)."""
    g.shoe.extend(reversed(cards))


class ValueTests(unittest.TestCase):
    def test_hand_values_and_soft_aces(self):
        self.assertEqual(hand_value(["AS", "KH"]), (21, True))
        self.assertEqual(hand_value(["AS", "6H"]), (17, True))
        self.assertEqual(hand_value(["AS", "6H", "9D"]), (16, False))
        self.assertEqual(hand_value(["AS", "AH", "9D"]), (21, True))
        self.assertEqual(hand_value(["KS", "QH", "5D"]), (25, False))
        self.assertEqual(hand_value(["10S", "9H"]), (19, False))


class BlackjackTests(unittest.TestCase):
    def bet_all(self, g, ids, amount=100):
        for pid in ids:
            g.handle(pid, {"a": "bet", "amount": amount})

    def test_bets_are_validated(self):
        g, ids, _ = make()
        for bad in (75, 0, True, "100", 5000, None):
            with self.assertRaises(GameError):
                g.handle("p0", {"a": "bet", "amount": bad})
        g.handle("p0", {"a": "bet", "amount": 100})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "bet", "amount": 200})  # already in
        with self.assertRaises(GameError):
            g.handle("p1", {"a": "hit"})  # not the play phase

    def test_dealer_hole_card_and_shoe_never_leak(self):
        g, ids, _ = make()
        rig(g, ["9S", "8S", "7S", "5D", "QH", "6C", "KD", "4H"])  # p0,p1,p2,dealer; p0,p1,p2,dealer
        self.bet_all(g, ids)
        hole = g.dealer[1]
        for viewer in [*ids, TV]:
            v = g.view_for(viewer)
            self.assertEqual(len(v["dealer"]["cards"]), 1)  # only the up card
            self.assertTrue(v["dealer"]["hidden"])
            self.assertNotIn("shoe", v)
            self.assertNotIn(hole, str(v["dealer"]))
        self.assertEqual(g.view_for("p0")["shoe_left"], len(g.shoe))

    def test_turns_hits_busts_dealer_draws_and_payouts(self):
        g, ids, _ = make()
        # Deal order: p0, p1, p2, dealer, then second cards in the same order.
        rig(g, ["10S", "9S", "AS", "10D", "6H", "9H", "KS", "6D", "QC", "2C"])
        self.bet_all(g, ids)
        # p0 16, p1 18, p2 blackjack; dealer 10 + 6 = 16 (hidden 6)
        self.assertEqual(g.phase, "play")
        self.assertEqual(g.view_for("p0")["turn"], {"player": "p0", "hand": 0})
        with self.assertRaises(GameError):
            g.handle("p1", {"a": "stand"})  # not your turn
        g.handle("p0", {"a": "hit"})  # 16 + Q = bust
        self.assertEqual(
            g.view_for("p0")["turn"]["player"], "p1"
        )  # bust ends your turn; p2's blackjack is skipped
        g.handle("p1", {"a": "stand"})
        # dealer 16 must draw: 2 -> 18, stands
        self.assertEqual(g.phase, "settle")
        r = g.view_for(TV)["result"]
        self.assertEqual(r["dealer_value"], 18)
        self.assertEqual(r["net"], {"p0": -100, "p1": 0, "p2": 150})  # bust, push, blackjack 3:2
        self.assertEqual(g.chips, {"p0": 900, "p1": 1000, "p2": 1150})

    def test_double_and_split(self):
        g, ids, _ = make(n=2)
        # p0: 8,8 (split); p1: 6,5 (double); dealer 10, 7
        rig(g, ["8S", "6H", "10D", "8D", "5C", "7H", "3S", "10C", "9H", "2D"])
        self.bet_all(g, ids)
        v = g.view_for("p0")
        self.assertIn("split", v["you"]["actions"])
        g.handle("p0", {"a": "split"})  # hands: 8S+3S, 8D+10C
        self.assertEqual(g.chips["p0"], 800)  # second bet taken
        g.handle("p0", {"a": "stand"})  # hand 0 (11) - silly, but legal
        g.handle("p0", {"a": "stand"})  # hand 1 (18)
        self.assertEqual(g.view_for("p1")["turn"]["player"], "p1")
        g.handle("p1", {"a": "double"})  # 6+5 = 11, double draws 9H -> 20, turn ends
        self.assertEqual(g.phase, "settle")  # dealer 17 stands
        net = g.view_for("p0")["result"]["net"]
        self.assertEqual(net["p0"], -100 + 100)  # 11 loses to 17, 18 beats 17
        self.assertEqual(net["p1"], 200)  # doubled win

    def test_dealer_blackjack_ends_the_hand_at_once(self):
        g, ids, _ = make(n=2)
        rig(g, ["10S", "9H", "AS", "9D", "8D", "KH"])  # p0 19, p1 17, dealer A + K
        self.bet_all(g, ids)
        self.assertEqual(g.phase, "settle")
        self.assertEqual(g.view_for("p0")["result"]["net"], {"p0": -100, "p1": -100})

    def test_timers_auto_bet_and_auto_stand_and_game_ends(self):
        g, ids, clock = make(n=2)
        for _ in range(BlackjackShowdown.HANDS):
            clock[0] += 60
            g.tick()  # bets close: everyone auto-bets the minimum
            while g.phase == "play":
                clock[0] += 60
                g.tick()  # each turn times out: stand
            self.assertEqual(g.phase, "settle")
            clock[0] += 60
            g.tick()
        self.assertTrue(g.finished)
        self.assertEqual(sum(g.scores().values()), sum(g.chips.values()) - 2000)

    def test_broke_players_sit_out(self):
        g, ids, clock = make(n=2)
        g.chips["p0"] = 20
        g.handle("p1", {"a": "bet", "amount": 50})
        self.assertNotEqual(g.phase, "bet")  # p0 can't afford the minimum: not waited for
        self.assertNotIn("p0", g.hands)


class FuzzTests(unittest.TestCase):
    def test_random_play_never_breaks_the_table(self):
        for seed in range(300):
            rnd = random.Random(seed)
            g, ids, clock = make(n=rnd.randint(2, 8), seed=seed)
            for _ in range(2000):
                if g.finished:
                    break
                if g.phase == "bet":
                    for pid in ids:
                        if pid not in g.bets and rnd.random() < 0.8 and g.chips[pid] >= 50:
                            affordable = [b for b in (50, 100, 200, 500) if b <= g.chips[pid]]
                            g.handle(pid, {"a": "bet", "amount": rnd.choice(affordable)})
                    if g.phase == "bet":
                        clock[0] += 30
                        g.tick()
                elif g.phase == "play":
                    who = g.view_for(TV)["turn"]["player"]
                    legal = g.view_for(who)["you"]["actions"]
                    if rnd.random() < 0.1:
                        clock[0] += 30
                        g.tick()  # a player wanders off: auto-stand
                    else:
                        g.handle(who, {"a": rnd.choice(legal)})
                    v = g.view_for(TV)
                    if g.phase == "play":
                        self.assertEqual(len(v["dealer"]["cards"]), 1)  # hole card still hidden
                elif g.phase == "settle":
                    r = g.result
                    if not r["dealer_blackjack"] and any(
                        o != "bust" for os in r["outcomes"].values() for o in os
                    ):
                        self.assertGreaterEqual(r["dealer_value"], 17)
                    clock[0] += 30
                    g.tick()
                for pid in ids:
                    self.assertGreaterEqual(g.chips[pid], 0)
            self.assertTrue(g.finished, f"seed {seed} never finished")
            self.assertEqual(sum(g.scores().values()), sum(g.chips.values()) - 1000 * len(ids))


if __name__ == "__main__":
    unittest.main()
