"""The host's Skip never hands a playing host a secret or someone else's turn; the clocks still run."""

from __future__ import annotations

import random
import unittest

from app.games import Player
from app.games.bomb import HotPotatoBomb
from app.games.mafia import MafiaNight
from app.games.reflex import ReactionDuel
from app.games.ships import Battleships
from app.games.trivia import TriviaTonight


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(cls, n):
    clock = Clock()
    g = cls([Player(id=f"p{i}", name=f"N{i}") for i in range(n)], rng=random.Random(2), clock=clock)
    g.start()
    return g, clock


class SkipTests(unittest.TestCase):
    def assert_refused_then_clock_moves(self, g, clock, phase):
        self.assertEqual(g.phase, phase)
        before = (g.phase, g.version)
        g.skip()
        self.assertEqual((g.phase, g.version), before)
        clock.t += 120
        g.tick()
        self.assertNotEqual(g.phase, phase)

    def test_bomb_cannot_be_set_off(self):
        g, clock = make(HotPotatoBomb, 4)
        self.assert_refused_then_clock_moves(g, clock, "pass")
        g.skip()  # the result screen can be skipped
        self.assertEqual(g.phase, "pass")

    def test_reflex_signal_cannot_be_called(self):
        g, clock = make(ReactionDuel, 3)
        self.assertEqual(g.phase, "wait")
        g.skip()
        self.assertEqual(g.phase, "wait")
        clock.t = g.go_at
        g.tick()
        self.assertEqual(g.phase, "go")
        g.skip()  # the stragglers can be skipped
        self.assertEqual(g.phase, "result")

    def test_battleships_placing_only(self):
        g, clock = make(Battleships, 2)
        g.skip()
        self.assertEqual(g.phase, "battle")
        g.skip()
        self.assertEqual(g.phase, "battle")
        self.assertEqual(g.shots, [{}, {}])  # no random shot fired for anyone
        clock.t += 120
        g.tick()
        self.assertEqual(sum(map(len, g.shots)), 1)  # the turn clock fires for someone really away

    def test_mafia_night_and_day_run_their_course(self):
        g, clock = make(MafiaNight, 6)
        g.skip()  # roles: fine
        self.assert_refused_then_clock_moves(g, clock, "night")
        g.skip()  # dawn: fine
        if g.phase == "day":
            self.assert_refused_then_clock_moves(g, clock, "day")

    def test_trivia_question_runs_its_clock(self):
        g, clock = make(TriviaTonight, 2)
        self.assert_refused_then_clock_moves(g, clock, "question")
        g.skip()  # the reveal: fine
        self.assertEqual((g.phase, g.round), ("question", 1))


if __name__ == "__main__":
    unittest.main()
