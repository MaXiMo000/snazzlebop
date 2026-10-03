"""Lowest Lonely Number: the winner rule, rollover, secrecy, input checks."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.lonely import POT, ROUNDS, LowestLonely, lonely_winner

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n, seed=1):
    clock = Clock()
    g = LowestLonely(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)], rng=random.Random(seed), clock=clock
    )
    g.start()
    return g, clock


def play(g, picks):
    for pid, n in picks.items():
        g.handle(pid, {"a": "pick", "n": n})
    if g.phase == "pick":
        g.advance()


class LonelyTests(unittest.TestCase):
    def test_winner_rule(self):
        self.assertEqual(lonely_winner({"a": 1, "b": 1, "c": 2}), "c")
        self.assertEqual(lonely_winner({"a": 3, "b": 2, "c": 5}), "b")
        self.assertIsNone(lonely_winner({"a": 4, "b": 4}))
        self.assertIsNone(lonely_winner({}))

    def test_pot_pays_the_lowest_lonely_and_ties_roll_over(self):
        g, _ = make(3)
        play(g, {"p0": 2, "p1": 2, "p2": 2})  # nobody lonely
        self.assertIsNone(g.result["winner"])
        self.assertEqual(g.rollover, POT)
        g.advance()
        self.assertEqual(g.view_for("p0")["pot"], 2 * POT)
        play(g, {"p0": 1, "p1": 1, "p2": 9})
        self.assertEqual(g.scores(), {"p0": 0, "p1": 0, "p2": 2 * POT})
        self.assertEqual(g.rollover, 0)

    def test_last_round_pays_double_and_nothing_rolls_past_the_end(self):
        g, _ = make(2)
        for _ in range(ROUNDS - 1):
            play(g, {"p0": 5, "p1": 5})
            g.advance()
        self.assertEqual(g.view_for("p0")["pot"], 2 * POT + (ROUNDS - 1) * POT)
        play(g, {"p0": 5, "p1": 5})
        g.advance()
        self.assertTrue(g.finished)
        self.assertEqual(g.rollover, 0)

    def test_no_pick_sits_the_round_out(self):
        g, clock = make(3)
        g.handle("p0", {"a": "pick", "n": 4})
        clock.t += g.timings["pick"] + 1
        g.tick()
        self.assertEqual(g.phase, "reveal")
        self.assertEqual(g.result["winner"], "p0")
        self.assertNotIn("p1", g.result["picks"])

    def test_picks_are_secret_until_the_reveal(self):
        g, _ = make(4)
        g.handle("p0", {"a": "pick", "n": 17})
        for viewer in ("p1", "p2", *SPECTATORS):
            view = g.view_for(viewer)
            self.assertNotIn("17", json.dumps(view))
            self.assertIsNone(view["you"]["pick"])
            self.assertEqual(view["locked"], ["p0"])
        self.assertEqual(g.view_for("p0")["you"]["pick"], 17)

    def test_input_validation(self):
        g, _ = make(2)
        for bad in (0, 21, -1, True, "3", None, 2.5):
            with self.assertRaises(GameError, msg=repr(bad)):
                g.handle("p0", {"a": "pick", "n": bad})
        g.handle("p0", {"a": "pick", "n": 3})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "pick", "n": 4})
        with self.assertRaises(GameError):
            g.handle("zz", {"a": "pick", "n": 4})

    def test_peek_names_a_taken_number_but_not_whose(self):
        g, _ = make(3)
        self.assertIsNone(g.peek("p0"))
        g.handle("p1", {"a": "pick", "n": 6})
        self.assertEqual(g.peek("p0"), "Someone has already picked 6.")
        self.assertIsNone(g.peek("p1"))  # your own pick doesn't count

    def test_highlights(self):
        g, _ = make(4)
        for _ in range(ROUNDS):
            play(g, {"p0": 1, "p1": 3, "p2": 3, "p3": 3})
            g.advance()
        titles = [h["title"] for h in g.highlights()]
        self.assertIn("Lone wolf", titles)
        self.assertIn("Crowd favourite", titles)


if __name__ == "__main__":
    unittest.main()
