"""Reaction Duel: the secret signal, fake-outs, false starts, ranking and points."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.reflex import EARLY, FAKES, PLACE_POINTS, TAPPED, ReactionDuel

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=4, seed=1, **opts):
    clock = Clock()
    g = ReactionDuel(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=clock,
        options=opts or None,
    )
    g.start()
    return g, clock


def to_go(g, clock):
    clock.t = g.go_at
    g.tick()


class ReflexTests(unittest.TestCase):
    def test_fastest_taps_rank_and_score(self):
        g, clock = make(5)
        self.assertEqual(g.phase, "wait")
        to_go(g, clock)
        self.assertEqual(g.phase, "go")
        for pid in ["p2", "p0", "p4", "p1", "p3"]:
            clock.t += 0.1
            g.handle(pid, {"a": "tap"})
        self.assertEqual(g.phase, "result")
        r = g.result
        self.assertEqual(list(r["times"]), ["p2", "p0", "p4", "p1", "p3"])
        self.assertEqual(r["times"]["p2"], 100)
        self.assertEqual(r["winner"], "p2")
        self.assertEqual(
            [g.round_scores[p] for p in ("p2", "p0", "p4", "p1", "p3")], [*PLACE_POINTS, TAPPED, TAPPED]
        )

    def test_false_start_costs_and_sits_out(self):
        g, clock = make(3)
        g.handle("p0", {"a": "tap"})
        self.assertEqual(g.view_for("tv:screen")["early"], ["p0"])
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "tap"})
        to_go(g, clock)
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "tap"})
        clock.t += 0.2
        g.handle("p1", {"a": "tap"})
        g.handle("p2", {"a": "tap"})
        self.assertEqual(g.phase, "result")
        self.assertEqual(g.round_scores, {"p0": EARLY, "p1": PLACE_POINTS[0], "p2": PLACE_POINTS[1]})

    def test_everyone_early_ends_the_round(self):
        g, _ = make(2)
        g.handle("p0", {"a": "tap"})
        g.handle("p1", {"a": "tap"})
        self.assertEqual((g.phase, g.result["winner"]), ("result", None))

    def test_slow_players_time_out(self):
        g, clock = make(3)
        to_go(g, clock)
        g.handle("p1", {"a": "tap"})
        clock.t += 3.1
        g.tick()
        self.assertEqual(g.phase, "result")
        self.assertEqual(g.round_scores, {"p0": 0, "p1": PLACE_POINTS[0], "p2": 0})

    def test_fake_outs_show_and_clear_before_the_signal(self):
        shown = set()
        for seed in range(40):
            g, clock = make(2, seed)
            for at, word, tone in g.fakes:
                self.assertIn(word, FAKES)
                self.assertLess(at + 0.8, g.go_at)
                clock.t = at + 0.1
                g.tick()
                fake = g.view_for("p0")["fake"]
                self.assertEqual((fake["word"], fake["tone"]), (word, tone))
                shown.add(word)
                clock.t = at + 0.9
                g.tick()
                self.assertIsNone(g.view_for("p0")["fake"])
                self.assertEqual(g.phase, "wait")
            to_go(g, clock)
            self.assertIsNone(g.view_for("p0")["fake"])
        self.assertNotIn("TAP!", FAKES)
        self.assertGreater(len(shown), 4)

    def test_the_signal_time_is_never_sent(self):
        for seed in range(10):
            g, clock = make(4, seed)
            for step in (0.0, 0.5, 1.2):
                clock.t = step
                g.tick()
                for viewer in [*g.player_ids, *SPECTATORS]:
                    view = g.view_for(viewer)
                    blob = json.dumps(view)
                    self.assertIsNone(view["remaining"])
                    for secret in ("go_at", "fakes", "go_time", '"at"'):
                        self.assertNotIn(secret, blob)
                    self.assertNotIn(str(round(g.go_at, 3)), blob)
            self.assertIsNone(g.view_for("tv:screen")["you"])
            self.assertTrue(2.5 <= g.go_at <= 7.0)

    def test_input_and_phases(self):
        g, clock = make(2)
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "press"})
        with self.assertRaises(GameError):
            g.handle("stranger", {"a": "tap"})
        to_go(g, clock)
        g.handle("p0", {"a": "tap"})
        g.handle("p1", {"a": "tap"})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "tap"})  # result screen

    def test_rounds_option_final_and_host_skip(self):
        g, clock = make(3, rounds="5")
        for rnd in range(1, 6):
            self.assertEqual((g.phase, g.round), ("wait", rnd))
            g.advance()  # skip the wait: the signal comes now
            self.assertEqual(g.phase, "go")
            g.handle("p1", {"a": "tap"})
            g.advance()  # skip the stragglers
            self.assertEqual(g.phase, "result")
            g.advance()
        self.assertTrue(g.finished)
        view = g.view_for("au:fan")
        self.assertEqual(view["wins"], {"p0": 0, "p1": 5, "p2": 0})
        self.assertEqual(view["scores"]["p1"], 5 * PLACE_POINTS[0])
        self.assertIn("p1", view["best"])

    def test_timers_alone_finish_the_game(self):
        g, clock = make(2)
        for _ in range(400):
            if g.finished:
                break
            clock.t += 0.5
            g.tick()
        self.assertTrue(g.finished)


if __name__ == "__main__":
    unittest.main()
