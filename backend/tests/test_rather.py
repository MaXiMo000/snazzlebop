"""Would You Rather: the hot seat rotation, scoring, timeouts, skip and secrecy in every phase."""

from __future__ import annotations

import json
import random
import unittest

from app.contentgen import v_rather
from app.games import GameError, Player
from app.games.content import RATHER
from app.games.rather import GUESS_POINTS, KNOWN_POINTS, WouldYouRather

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=4, seed=1, **opts):
    clock = Clock()
    g = WouldYouRather(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=clock,
        options=opts or None,
    )
    g.start()
    return g, clock


class RatherTests(unittest.TestCase):
    def test_pool(self):
        self.assertGreater(len(RATHER), 200)
        self.assertEqual(len({(d["a"], d["b"]) for d in RATHER}), len(RATHER))

    def test_scoring(self):
        g, _ = make(4)
        hot = g.hot
        others = [p for p in g.player_ids if p != hot]
        g.handle(hot, {"a": "answer", "pick": 1})
        g.handle(others[0], {"a": "answer", "pick": 0, "guess": 1})  # read them right
        g.handle(others[1], {"a": "answer", "pick": 1, "guess": 1})  # right too
        self.assertEqual(g.phase, "pick")
        g.handle(others[2], {"a": "answer", "pick": 1, "guess": 0})  # wrong
        self.assertEqual(g.phase, "reveal")
        r = g.result
        self.assertEqual(r["right"], sorted(others[:2]))
        self.assertEqual(r["split"], [1, 3])
        self.assertEqual(r["gains"][hot], 2 * KNOWN_POINTS)
        self.assertEqual(r["gains"][others[0]], GUESS_POINTS)
        self.assertEqual(r["gains"][others[2]], 0)

    def test_everyone_takes_the_hot_seat(self):
        g, clock = make(3, laps="2")
        seats = []
        while not g.finished:
            seats.append(g.hot)
            clock.t += 100
            g.tick()
            clock.t += 100
            g.tick()
        self.assertEqual(len(seats), 6)
        self.assertEqual(sorted(seats), sorted(g.player_ids * 2))
        self.assertEqual(seats[:3], seats[3:])

    def test_input_checks(self):
        g, _ = make(3)
        other = next(p for p in g.player_ids if p != g.hot)
        for bad in (
            {"a": "answer", "pick": 2, "guess": 0},
            {"a": "answer", "pick": True, "guess": 0},
            {"a": "answer", "pick": 0},  # a guess is needed unless you're the hot seat
            {"a": "nope"},
        ):
            with self.assertRaises(GameError):
                g.handle(other, bad)
        g.handle(g.hot, {"a": "answer", "pick": 0})  # the hot seat doesn't guess
        with self.assertRaises(GameError):
            g.handle(g.hot, {"a": "answer", "pick": 1})  # locked
        with self.assertRaises(GameError):
            g.handle("tv:screen", {"a": "answer", "pick": 0})

    def test_silent_hot_seat_scores_nobody_and_skip_waits_for_the_clock(self):
        g, clock = make(3)
        for p in g.player_ids:
            if p != g.hot:
                g.handle(p, {"a": "answer", "pick": 0, "guess": 0})
        self.assertFalse(g.skip())  # still deciding: a host can't cut the round short
        self.assertEqual(g.phase, "pick")
        clock.t += 30
        g.tick()
        self.assertEqual(g.phase, "reveal")
        self.assertIsNone(g.result["choice"])
        self.assertEqual(sum(g.result["gains"].values()), 0)
        self.assertTrue(g.skip())  # the reveal can be skipped
        self.assertEqual(g.phase, "pick")

    def test_secrecy_every_phase(self):
        g, clock = make(4)
        while not g.finished:
            if g.phase == "pick":
                first = g.player_ids[0]
                g.handle(first, {"a": "answer", "pick": 1, **({} if first == g.hot else {"guess": 0})})
                for viewer in [*g.player_ids, *SPECTATORS]:
                    v = g.view_for(viewer)
                    json.dumps(v)
                    self.assertNotIn("result", v)
                    self.assertEqual(v["locked"], [first])  # who, never what
                    if viewer != first and v["you"] is not None:
                        self.assertIsNone(v["you"]["pick"])
                        self.assertIsNone(v["you"]["guess"])
                self.assertEqual(g.view_for(first)["you"]["pick"], 1)
                line = g.peek(g.player_ids[1]) if g.player_ids[1] != g.hot else None
                if line:
                    self.assertNotIn(g.name_of(g.hot), line)
            clock.t += 100
            g.tick()
        for viewer in [*g.player_ids, *SPECTATORS]:
            v = g.view_for(viewer)
            json.dumps(v)
            self.assertEqual(len(v["history"]), 4)
        self.assertIsNone(g.view_for("tv:screen")["you"])
        json.dumps(g.highlights())

    def test_generated_dilemmas_are_checked(self):
        self.assertEqual(
            v_rather({"a": "ride a dragon", "b": "ride a whale"}), {"a": "ride a dragon", "b": "ride a whale"}
        )
        for bad in (
            {"a": "x", "b": "ride a whale"},
            {"a": "same", "b": "SAME"},
            {"a": "fly?", "b": "swim"},
            "nope",
        ):
            self.assertIsNone(v_rather(bad))


if __name__ == "__main__":
    unittest.main()
