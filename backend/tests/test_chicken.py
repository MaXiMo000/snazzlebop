"""Chicken Run: exact cash-out values on an injected clock, a bomb nobody can see, late taps, the bonus."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.chicken import NERVE_BONUS, ROUNDS, ChickenRun, value_at

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def make(n=3, seed=1):
    clock = Clock()
    g = ChickenRun([Player(id=f"p{i}", name=f"N{i}") for i in range(n)], rng=random.Random(seed), clock=clock)
    g.start()
    return g, clock


def run(g, clock):
    clock.t += 3.0
    g.tick()  # ready -> run
    assert g.phase == "run"


class ChickenTests(unittest.TestCase):
    def test_the_value_grows_and_cash_outs_bank_it(self):
        self.assertEqual([value_at(t) for t in (0, 5, 10, 20)], [20, 40, 80, 327])
        g, clock = make(2)
        g.bomb = 15.0
        run(g, clock)
        clock.t += 5.0
        g.handle("p0", {"a": "cash"})
        self.assertEqual(g.cashed["p0"], {"t": 5.0, "value": 40})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "cash"})
        clock.t += 5.0
        g.handle("p1", {"a": "cash"})  # everyone's out: the round ends at once
        self.assertEqual(g.phase, "boom")
        self.assertEqual(g.scores(), {"p0": 40, "p1": 80 + NERVE_BONUS})
        self.assertEqual(g.result["bomb"], 15.0)

    def test_the_bomb_is_secret_and_no_countdown_gives_it_away(self):
        g, clock = make(3)
        g.bomb = 17.25
        for phase_step in range(2):
            if phase_step:
                run(g, clock)
            for viewer in ("p0", *SPECTATORS):
                view = g.view_for(viewer)
                self.assertNotIn("result", view)
                self.assertNotIn("17.25", json.dumps(view))
                if g.phase == "run":
                    self.assertIsNone(view["remaining"])

    def test_the_published_time_and_value_always_agree(self):
        g, clock = make(2)
        g.bomb = 20.0
        run(g, clock)
        clock.t += 2.6571  # rounds to 2.66: the value must be the one for 2.66, not 2.6571
        g.handle("p0", {"a": "cash"})
        c = g.cashed["p0"]
        self.assertEqual((c["t"], c["value"]), (2.66, value_at(2.66)))

    def test_late_taps_lose_and_set_off_the_bomb(self):
        g, clock = make(3)
        g.bomb = 6.0
        run(g, clock)
        clock.t += 2.0
        g.handle("p0", {"a": "cash"})
        clock.t += 5.0  # 7 s: the bomb went off at 6 s, between ticks
        with self.assertRaises(GameError):
            g.handle("p1", {"a": "cash"})
        self.assertEqual(g.phase, "boom")
        self.assertEqual(sorted(g.result["boomed"]), ["p1", "p2"])
        self.assertEqual(g.scores()["p1"], 0)
        self.assertEqual(g.scores()["p0"], value_at(2.0) + NERVE_BONUS)

    def test_the_ticker_sets_off_the_bomb(self):
        g, clock = make(2)
        g.bomb = 4.5
        run(g, clock)
        clock.t += 4.4
        g.tick()
        self.assertEqual(g.phase, "run")
        clock.t += 0.2
        g.tick()
        self.assertEqual(g.phase, "boom")

    def test_no_bonus_on_a_tie_and_the_game_ends_after_five_rounds(self):
        g, clock = make(2)
        g.bomb = 20.0
        run(g, clock)
        clock.t += 3.0
        g.handle("p0", {"a": "cash"})
        g.handle("p1", {"a": "cash"})  # same instant, same value
        self.assertIsNone(g.result["nerve"])
        for _ in range(ROUNDS * 3):
            g.advance()
        self.assertTrue(g.finished)
        self.assertEqual(len(g.history), ROUNDS)
        for bomb in (h["bomb"] for h in g.history):
            self.assertTrue(4.0 <= bomb <= 24.0)

    def test_wrong_phase_and_bad_actions(self):
        g, _ = make(2)
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "cash"})  # still the get-ready
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "bomb"})
        with self.assertRaises(GameError):
            g.handle("intruder", {"a": "cash"})


if __name__ == "__main__":
    unittest.main()
