"""Code Crackers: Mastermind feedback, cracking order and points, privacy, cooldown, endings."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.codes import COOLDOWN, HINT_COST, UNCRACKED_POINTS, CodeCrackers, feedback

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make(n=3, codes=None):
    clock = Clock()
    g = CodeCrackers([Player(id=f"p{i}", name=f"N{i}") for i in range(n)], rng=random.Random(1), clock=clock)
    g.start()
    for pid, code in (codes or {}).items():
        g.handle(pid, {"a": "set", "code": code})
    return g, clock


class FeedbackTests(unittest.TestCase):
    def test_mastermind_feedback(self):
        self.assertEqual(feedback([0, 1, 2, 3], [0, 1, 2, 3]), (4, 0))
        self.assertEqual(feedback([0, 1, 2, 3], [3, 2, 1, 0]), (0, 4))
        self.assertEqual(feedback([0, 0, 1, 1], [0, 1, 0, 5]), (1, 2))
        self.assertEqual(feedback([5, 5, 5, 5], [5, 0, 0, 0]), (1, 0))  # one 5 can't count twice
        self.assertEqual(feedback([1, 2, 3, 4], [5, 5, 5, 5]), (0, 0))


class CodesTests(unittest.TestCase):
    def test_cracking_order_scores_and_the_uncracked_bonus(self):
        g, clock = make(3, {"p0": [0, 1, 2, 3], "p1": [4, 4, 4, 4], "p2": [5, 0, 5, 0]})
        self.assertEqual(g.phase, "crack")
        g.handle("p1", {"a": "guess", "target": "p0", "code": [0, 1, 2, 3]})
        clock.t += COOLDOWN
        g.handle("p2", {"a": "guess", "target": "p0", "code": [0, 1, 2, 3]})
        self.assertEqual(g.cracked["p0"], ["p1", "p2"])
        self.assertEqual((g.scores()["p1"], g.scores()["p2"]), (300, 200))
        with self.assertRaises(GameError):
            g.handle("p1", {"a": "guess", "target": "p0", "code": [0, 1, 2, 3]})  # already cracked
        g.advance()  # time's up: p1 and p2 were never cracked
        self.assertTrue(g.finished)
        self.assertEqual(g.scores()["p1"], 300 + UNCRACKED_POINTS)
        self.assertEqual(g.scores()["p0"], 0)

    def test_codes_and_guesses_are_private_until_the_end(self):
        g, clock = make(3, {"p0": [0, 1, 2, 3], "p1": [5, 4, 3, 2], "p2": [1, 1, 1, 1]})
        g.handle("p1", {"a": "guess", "target": "p0", "code": [0, 0, 0, 0]})
        for viewer in ("p0", "p2", *SPECTATORS):
            view = g.view_for(viewer)
            self.assertNotIn("codes", view)
            self.assertEqual(view["you"]["guesses"], {})
            self.assertNotIn("[5, 4, 3, 2]", json.dumps(view))  # p1's code
        self.assertEqual(
            g.view_for("p1")["you"]["guesses"]["p0"], [{"code": [0, 0, 0, 0], "hits": 1, "near": 0}]
        )
        self.assertEqual(g.view_for("tv:x")["guess_counts"]["p1"], 1)
        g.advance()
        self.assertEqual(g.view_for("tv:x")["codes"]["p1"], [5, 4, 3, 2])

    def test_cooldown_between_guesses(self):
        g, clock = make(2, {"p0": [0, 0, 0, 0], "p1": [1, 1, 1, 1]})
        g.handle("p0", {"a": "guess", "target": "p1", "code": [2, 2, 2, 2]})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "guess", "target": "p1", "code": [3, 3, 3, 3]})
        clock.t += COOLDOWN
        g.handle("p0", {"a": "guess", "target": "p1", "code": [3, 3, 3, 3]})

    def test_the_race_ends_when_every_code_is_cracked(self):
        g, clock = make(2, {"p0": [0, 0, 0, 0], "p1": [1, 1, 1, 1]})
        g.handle("p0", {"a": "guess", "target": "p1", "code": [1, 1, 1, 1]})
        g.handle("p1", {"a": "guess", "target": "p0", "code": [0, 0, 0, 0]})
        self.assertTrue(g.finished)

    def test_unset_codes_are_random_and_input_is_validated(self):
        g, _ = make(3)
        for bad in ([0, 1, 2], [0, 1, 2, 6], [0, 1, 2, True], "0123", [0.0, 1, 2, 3]):
            with self.assertRaises(GameError, msg=repr(bad)):
                g.handle("p0", {"a": "set", "code": bad})
        g.handle("p0", {"a": "set", "code": [1, 2, 3, 4]})
        g.advance()  # the others never set one
        self.assertEqual(g.phase, "crack")
        self.assertTrue(all(len(c) == 4 and all(0 <= x < 6 for x in c) for c in g.codes.values()))
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "guess", "target": "p0", "code": [1, 2, 3, 4]})  # not your own
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "guess", "target": "nobody", "code": [1, 2, 3, 4]})


class CodesToolsTests(unittest.TestCase):
    def setup_game(self, decoy_for=()):
        g, self.clock = make(3)
        codes = {"p0": [0, 1, 2, 3], "p1": [4, 4, 5, 5], "p2": [1, 1, 1, 1]}
        for pid, code in codes.items():
            g.handle(pid, {"a": "set", "code": code, "decoy": pid in decoy_for})
        self.assertEqual(g.phase, "crack")
        return g

    def test_hints_cost_points_go_left_to_right_and_stop_at_two(self):
        g = self.setup_game()
        g.handle("p0", {"a": "hint", "target": "p1"})
        g.handle("p0", {"a": "hint", "target": "p1"})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "hint", "target": "p1"})
        self.assertEqual(
            g.view_for("p0")["you"]["hints"]["p1"], [{"pos": 0, "symbol": 4}, {"pos": 1, "symbol": 4}]
        )
        self.assertEqual(g.scores()["p0"], -2 * HINT_COST)
        self.assertEqual(g.view_for("p2")["you"]["hints"], {})  # private
        self.assertEqual(g.view_for("p2")["hint_counts"]["p0"], 2)  # the count is public

    def test_decoy_fools_the_first_guess_then_owns_up(self):
        g = self.setup_game(decoy_for=("p1",))
        self.assertTrue(g.view_for("p1")["you"]["decoy"])
        self.assertFalse(g.view_for("p0")["you"]["decoy"])
        decoy = list(g.decoys["p1"])
        self.assertNotEqual(decoy, [4, 4, 5, 5])
        guess = [0, 0, 0, 0]
        g.handle("p0", {"a": "guess", "target": "p1", "code": guess})
        entry = g.guesses["p0"]["p1"][0]
        self.assertTrue(entry["decoy"])
        self.assertEqual((entry["hits"], entry["near"]), feedback(decoy, guess))
        shown = g.view_for("p0")["you"]["guesses"]["p1"][0]
        self.assertNotIn("decoy", shown)  # not flagged yet
        self.assertEqual(g.view_for("p2")["decoy_sprung"], ["p1"])
        self.clock.t += 2
        g.handle("p0", {"a": "guess", "target": "p1", "code": [4, 4, 5, 0]})
        shown = g.view_for("p0")["you"]["guesses"]["p1"]
        self.assertTrue(shown[0]["decoy"])  # revealed by the next guess
        self.assertEqual((shown[1]["hits"], shown[1]["near"]), (3, 0))  # the real code again

    def test_decoy_never_blocks_a_real_crack(self):
        g = self.setup_game(decoy_for=("p1",))
        g.handle("p0", {"a": "guess", "target": "p1", "code": [4, 4, 5, 5]})
        self.assertEqual(g.cracked["p1"], ["p0"])
        self.assertIn("p1", g.decoys)  # still armed for the next guesser

    def test_decoy_flag_must_be_a_bool(self):
        g, _ = make(2)
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "set", "code": [0, 0, 0, 0], "decoy": "yes"})


if __name__ == "__main__":
    unittest.main()
