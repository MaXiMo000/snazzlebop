"""Chicken Run: exact cash-out values on an injected clock, a bomb nobody can see, late taps, the bonus."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.chicken import (
    FUSE_COST,
    INSURANCE_COST,
    NERVE_BONUS,
    ROUNDS,
    ChickenRun,
    value_at,
)

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
    clock.t += g.timings["ready"]
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


class ChickenTrickTests(unittest.TestCase):
    def test_insurance_costs_up_front_and_pays_a_quarter_on_a_boom(self):
        g, clock = make(2)
        g.bomb = 10.0
        g.handle("p0", {"a": "insure"})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "insure"})
        self.assertEqual(g.scores()["p0"], -INSURANCE_COST)
        self.assertEqual(g.view_for("p1")["insured"], ["p0"])
        run(g, clock)
        clock.t += 11
        g.tick()  # boom: nobody cashed
        self.assertEqual(g.result["payouts"], {"p0": int(value_at(10.0) * 0.25)})
        self.assertEqual(g.scores()["p0"], -INSURANCE_COST + int(value_at(10.0) * 0.25))
        self.assertEqual(g.result["extras"]["p0"], g.scores()["p0"])

    def test_insured_and_cashed_out_just_pays_the_premium(self):
        g, clock = make(2)
        g.bomb = 10.0
        g.handle("p0", {"a": "insure"})
        run(g, clock)
        clock.t += 2
        g.handle("p0", {"a": "cash"})
        clock.t += 9
        g.tick()
        self.assertEqual(g.result["payouts"], {})
        self.assertEqual(g.scores()["p0"], value_at(2.0) - INSURANCE_COST + NERVE_BONUS)

    def test_short_fuse_blows_the_target_early_and_stays_secret(self):
        g, clock = make(3)
        g.bomb = 20.0
        g.handle("p0", {"a": "fuse", "target": "p1"})
        fuse = g.fuses["p1"]
        self.assertTrue(8.0 <= fuse <= 16.0)
        self.assertEqual(g.scores()["p0"], -FUSE_COST)
        self.assertTrue(g.view_for("p1")["you"]["fused"])
        for viewer in ("p0", "p2", *SPECTATORS):
            view = g.view_for(viewer)
            self.assertFalse(view["you"]["fused"])
            self.assertNotIn("result", view)
            self.assertNotIn(str(round(fuse, 2)), json.dumps(view))
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "fuse", "target": "p2"})  # once a game
        run(g, clock)
        clock.t += fuse + 0.1
        with self.assertRaises(GameError):
            g.handle("p1", {"a": "cash"})  # their fuse went off
        g.handle("p2", {"a": "cash"})  # the real bomb hasn't
        clock.t = clock.t + 20
        g.tick()
        self.assertIn("p1", g.result["boomed"])
        self.assertEqual(g.result["saboteurs"], {"p1": ["p0"]})

    def test_trick_rules(self):
        g, clock = make(2)
        for bad in (None, "p0", "zz", 3):
            with self.assertRaises(GameError, msg=repr(bad)):
                g.handle("p0", {"a": "fuse", "target": bad})
        run(g, clock)
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "insure"})  # too late: the run started

    def test_peek_gives_a_safe_window_below_your_bomb(self):
        g, _ = make(2)
        g.bomb = 20.0
        self.assertIn("15 seconds", g.peek("p0"))


if __name__ == "__main__":
    unittest.main()
