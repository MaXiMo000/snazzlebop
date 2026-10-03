"""Liar's Dice: secrecy, bidding rules, challenges, knockouts, timers, and a random-play fuzz."""

from __future__ import annotations

import random
import unittest

from app.games import GameError, Player
from app.games.dice import LiarsDice, dice_for

SPECTATORS = ("tv:screen", "au:fan")


def make(n=3, seed=1):
    g = LiarsDice([Player(id=f"p{i}", name=f"N{i}") for i in range(n)], rng=random.Random(seed))
    g.start()
    return g


def rig(g, dice, turn="p0"):
    g.dice = {p: sorted(d) for p, d in dice.items()}
    g.counts = {p: len(d) for p, d in dice.items()}
    g.turn = turn
    g.bid = None


class LiarsDiceTests(unittest.TestCase):
    def test_dice_are_secret(self):
        g = make(3)
        for viewer in ("p0", "p1", *SPECTATORS):
            view = g.view_for(viewer)
            self.assertNotIn("last", view)
            self.assertEqual(view["you"]["dice"], g.dice.get(viewer, []))
        self.assertEqual(g.view_for("tv:x")["you"]["dice"], [])
        self.assertEqual(g.view_for("p1")["counts"], {"p0": 5, "p1": 5, "p2": 5})

    def test_table_size_sets_the_dice(self):
        self.assertEqual([dice_for(n) for n in (2, 3, 4, 5, 6, 8)], [5, 5, 4, 4, 3, 3])

    def test_bids_must_rise_and_only_on_your_turn(self):
        g = make(3)
        rig(g, {"p0": [2, 3], "p1": [4, 5], "p2": [6, 6]})
        with self.assertRaises(GameError):
            g.handle("p1", {"a": "bid", "qty": 1, "face": 3})  # not p1's turn
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "liar"})  # nothing to challenge
        g.handle("p0", {"a": "bid", "qty": 2, "face": 3})
        for bad in (
            {"qty": 2, "face": 3},
            {"qty": 1, "face": 6},
            {"qty": 2, "face": 1},
            {"qty": 7, "face": 4},
            {"qty": True, "face": 4},
        ):
            with self.assertRaises(GameError, msg=bad):
                g.handle("p1", {"a": "bid", **bad})
        g.handle("p1", {"a": "bid", "qty": 2, "face": 5})  # same count, higher face
        g.handle("p2", {"a": "bid", "qty": 3, "face": 2})  # more dice
        self.assertEqual(g.bid, {"player": "p2", "qty": 3, "face": 2})
        self.assertEqual(g.turn, "p0")

    def test_ones_are_wild(self):
        g = make(2)
        rig(g, {"p0": [1, 4], "p1": [1, 1, 4]})
        self.assertEqual(g.count_face(4), 5)

    def test_liar_loses_when_the_bid_was_true_and_the_bidder_when_not(self):
        g = make(2)
        rig(g, {"p0": [4, 4, 2], "p1": [1, 3, 5]})
        g.handle("p0", {"a": "bid", "qty": 3, "face": 4})  # true: 4, 4 and a wild 1
        g.handle("p1", {"a": "liar"})
        self.assertEqual(g.last["loser"], "p1")
        self.assertEqual(g.counts, {"p0": 3, "p1": 2})
        # The reveal shows that round's dice to everyone, spectators included.
        self.assertEqual(g.view_for("tv:x")["last"]["dice"], {"p0": [2, 4, 4], "p1": [1, 3, 5]})
        g.advance()  # next round: the loser opens
        self.assertEqual(g.turn, "p1")
        rig(g, {"p0": [2, 2, 2], "p1": [3, 3]}, turn="p1")
        g.handle("p1", {"a": "bid", "qty": 4, "face": 3})  # false: only two 3s
        g.handle("p0", {"a": "liar"})
        self.assertEqual(g.last["loser"], "p1")

    def test_spot_on_wins_a_die_back_up_to_the_start_or_costs_one(self):
        g = make(2)
        rig(g, {"p0": [5, 5], "p1": [1, 2, 3]})
        g.handle("p0", {"a": "bid", "qty": 3, "face": 5})  # exactly three: 5, 5 and a wild 1
        g.handle("p1", {"a": "spot"})
        self.assertIsNone(g.last["loser"])
        self.assertEqual(g.counts["p1"], 4)  # 3 dice, under the 5 it started with: one back
        self.assertEqual(g.last["gained"], "p1")
        g2 = make(2)
        rig(g2, {"p0": [5, 5, 5, 5, 5], "p1": [5, 2, 2, 2, 2]})
        g2.handle("p0", {"a": "bid", "qty": 6, "face": 5})
        g2.handle("p1", {"a": "spot"})  # exact, but p1 already has the full 5 dice: no gain
        self.assertEqual(g2.counts["p1"], 5)
        g3 = make(2)
        rig(g3, {"p0": [5, 5], "p1": [2, 3]})
        g3.handle("p0", {"a": "bid", "qty": 3, "face": 5})
        g3.handle("p1", {"a": "spot"})  # wrong: only two
        self.assertEqual(g3.last["loser"], "p1")

    def test_knockouts_and_placement_scoring(self):
        g = make(3)
        rig(g, {"p0": [6], "p1": [2], "p2": [3, 4]})
        g.handle("p0", {"a": "bid", "qty": 1, "face": 5})  # false
        g.handle("p1", {"a": "liar"})  # p0 loses its last die
        self.assertEqual(g.out, ["p0"])
        g.advance()
        rig(g, {"p1": [2], "p2": [3]}, turn="p1")
        g.counts["p0"] = 0
        g.handle("p1", {"a": "bid", "qty": 2, "face": 2})  # false
        g.handle("p2", {"a": "liar"})
        g.advance()
        self.assertTrue(g.finished)
        self.assertEqual(g.standings, ["p2", "p1", "p0"])
        self.assertEqual(g.scores(), {"p2": 200 + 300, "p1": 100, "p0": 0})

    def test_timers_open_with_the_minimum_then_call_liar(self):
        g = make(2)
        opener = g.turn
        g.advance()
        self.assertEqual(g.bid, {"player": opener, "qty": 1, "face": 2})
        g.advance()
        self.assertEqual(g.phase, "reveal")

    def test_random_games_always_end_and_dice_add_up(self):
        for seed in range(300):
            rng = random.Random(seed)
            n = rng.randint(2, 8)
            g = make(n, seed)
            for _ in range(2000):
                if g.finished:
                    break
                if g.phase == "reveal":
                    g.advance()
                    continue
                before = sum(g.counts.values())
                r = rng.random()
                if g.bid is None or r < 0.6:
                    q = (g.bid["qty"] if g.bid else 0) + rng.choice([0, 1])
                    f = rng.randint(2, 6)
                    try:
                        g.handle(g.turn, {"a": "bid", "qty": max(q, 1), "face": f})
                    except GameError:
                        g.handle(g.turn, {"a": "liar"} if g.bid else {"a": "bid", "qty": 1, "face": 2})
                else:
                    g.handle(g.turn, {"a": "liar" if r < 0.9 else "spot"})
                    change = sum(g.counts.values()) - before
                    self.assertIn(change, (-1, 0, 1))
            self.assertTrue(g.finished, f"seed {seed} never finished")
            self.assertEqual(sorted(g.standings), sorted(g.player_ids))
            self.assertEqual(len(g.alive()), 1)


class PalificoTests(unittest.TestCase):
    def drop_to_one(self, n=3):
        """p0 bids five 6s with no 6s or ones anywhere: p1 calls liar, p0 drops to their last die."""
        g = make(n)
        rig(g, {"p0": [2, 3], **{f"p{i}": [2, 3, 4] for i in range(1, n)}})
        g.handle("p0", {"a": "bid", "qty": 5, "face": 6})
        g.handle("p1", {"a": "liar"})
        self.assertEqual(g.counts["p0"], 1)
        g.advance()
        return g

    def test_last_die_triggers_one_palifico_round_opened_by_that_player(self):
        g = self.drop_to_one()
        self.assertTrue(g.palifico)
        self.assertEqual(g.turn, "p0")
        self.assertTrue(g.view_for("p2")["palifico"])

    def test_ones_are_not_wild_and_the_face_is_fixed(self):
        g = self.drop_to_one()
        g.dice = {"p0": [1], "p1": [1, 1, 4], "p2": [4, 5, 6]}
        g.handle("p0", {"a": "bid", "qty": 1, "face": 4})
        with self.assertRaises(GameError):
            g.handle("p1", {"a": "bid", "qty": 2, "face": 5})  # can't change face
        with self.assertRaises(GameError):
            g.handle("p1", {"a": "bid", "qty": 1, "face": 4})  # must raise the count
        g.handle("p1", {"a": "bid", "qty": 3, "face": 4})
        g.handle("p2", {"a": "liar"})  # only two 4s: ones don't count
        self.assertEqual(g.last["actual"], 2)
        self.assertTrue(g.last["palifico"])
        self.assertEqual(g.last["loser"], "p1")

    def test_ones_can_be_bid_in_palifico_only(self):
        g = self.drop_to_one()
        g.handle("p0", {"a": "bid", "qty": 1, "face": 1})
        self.assertEqual(g.bid["face"], 1)
        g2 = make(3)
        with self.assertRaises(GameError):
            g2.handle(g2.turn, {"a": "bid", "qty": 1, "face": 1})

    def test_once_per_player_and_not_heads_up(self):
        g = self.drop_to_one()
        g.dice = {"p0": [3], "p1": [3, 4, 5], "p2": [3, 4, 5]}
        g.handle("p0", {"a": "bid", "qty": 1, "face": 2})
        g.handle("p1", {"a": "bid", "qty": 7, "face": 2})
        g.handle("p2", {"a": "liar"})  # no 2s: p1 drops to 2 dice
        g.advance()
        self.assertFalse(g.palifico)
        # p0 wins a die back, then drops to one again: no second palifico for them.
        rig(g, {"p0": [2, 3], "p1": [2, 3], "p2": [2, 3]})
        g.handle("p0", {"a": "bid", "qty": 6, "face": 6})
        g.handle("p1", {"a": "liar"})
        g.advance()
        self.assertFalse(g.palifico)
        two = make(2)
        rig(two, {"p0": [2, 3], "p1": [2, 3]})
        two.handle("p0", {"a": "bid", "qty": 4, "face": 6})
        two.handle("p1", {"a": "liar"})
        two.advance()
        self.assertFalse(two.palifico)  # heads-up: no palifico


if __name__ == "__main__":
    unittest.main()
