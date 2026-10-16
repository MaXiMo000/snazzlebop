"""Four in a Row: gravity, every kind of line, draws, turns (and team turns), clocks, best of 3, views."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.four import COLS, DRAW_POINTS, ROWS, WIN_POINTS, FourInARow, four_at

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=2, seed=1, teams=None, **opts):
    clock = Clock()
    g = FourInARow(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=clock,
        options=opts or None,
        teams=teams,
    )
    g.start()
    return g, clock


def play(g, cols):
    for c in cols:
        g.handle(g.mover, {"a": "drop", "col": c})


class LineTests(unittest.TestCase):
    def test_lines(self):
        cols = [[] for _ in range(COLS)]
        for c in range(4):
            cols[c].append(0)
        self.assertEqual(four_at(cols, 3, 0), [(0, 0), (1, 0), (2, 0), (3, 0)])
        cols = [[0, 0, 0, 0]] + [[] for _ in range(COLS - 1)]
        self.assertEqual(len(four_at(cols, 0, 3)), 4)
        # a rising diagonal, built on steps of the other colour
        cols = [[0], [1, 0], [1, 1, 0], [1, 1, 1, 0], [], [], []]
        self.assertEqual(four_at(cols, 3, 3), [(0, 0), (1, 1), (2, 2), (3, 3)])
        cols = [[1, 1, 1, 0], [1, 1, 0], [1, 0], [0], [], [], []]
        self.assertEqual(len(four_at(cols, 0, 3)), 4)
        cols = [[0], [0], [0], [], [], [], []]
        self.assertEqual(four_at(cols, 2, 0), [])


class GameTests(unittest.TestCase):
    def test_win_and_points(self):
        g, _ = make(2, match="1")
        red = g.sides[g.turn][0]
        play(g, [0, 6, 1, 6, 2, 6, 3])  # the starting side lines up four across the bottom
        self.assertEqual(g.phase, "over")
        self.assertEqual(g.winner, g.side_of[red])
        self.assertEqual(g.scores()[red], WIN_POINTS)
        self.assertEqual(len(g.view_for("tv:screen")["line"]), 4)
        g.skip()
        self.assertTrue(g.finished)

    def test_turns_and_bad_moves(self):
        g, _ = make(2)
        other = next(p for p in g.player_ids if p != g.mover)
        with self.assertRaises(GameError):
            g.handle(other, {"a": "drop", "col": 0})
        for bad in (-1, 7, True, "3", None):
            with self.assertRaises(GameError):
                g.handle(g.mover, {"a": "drop", "col": bad})
        for _ in range(ROWS):
            g.handle(g.mover, {"a": "drop", "col": 0})
        with self.assertRaises(GameError):
            g.handle(g.mover, {"a": "drop", "col": 0})  # full
        with self.assertRaises(GameError):
            g.handle("tv:screen", {"a": "drop", "col": 1})

    def test_draw(self):
        g, _ = make(2, match="1")
        # a known full board with no four: columns filled in pairs so colours alternate in bands
        order = [
            0,
            1,
            0,
            1,
            1,
            0,
            1,
            0,
            0,
            1,
            0,
            1,
            2,
            3,
            2,
            3,
            3,
            2,
            3,
            2,
            2,
            3,
            2,
            3,
            4,
            5,
            4,
            5,
            5,
            4,
            5,
            4,
            4,
            5,
            4,
            5,
        ]
        order += [6] * 6
        play(g, order)
        self.assertEqual((g.phase, g.winner), ("over", None))
        self.assertTrue(all(v == DRAW_POINTS for v in g.scores().values()))

    def test_teams_take_turns_and_have_a_channel(self):
        teams = {"p0": 0, "p1": 1, "p2": 0, "p3": 1}
        g, _ = make(4, teams=teams)
        self.assertEqual(sorted(g.sides[0]), ["p0", "p2"])
        movers = []
        for c in (0, 1, 2, 3):
            movers.append(g.mover)
            g.handle(g.mover, {"a": "drop", "col": c})
        side = g.side_of[movers[0]]
        self.assertNotEqual(movers[0], movers[2])  # teammates alternate
        self.assertEqual(g.side_of[movers[2]], side)
        self.assertEqual(g.chat_team("p0"), g.chat_team("p2"))
        self.assertNotEqual(g.chat_team("p0"), g.chat_team("p1"))
        g2, _ = make(2)
        self.assertIsNone(g2.chat_team("p0"))  # a side of one has nobody to talk to

    def test_clock_drops_for_an_absent_side_and_skip_waits(self):
        g, clock = make(2)
        self.assertFalse(g.skip())
        self.assertEqual(len(g.moves), 0)
        clock.t += 30
        g.tick()
        self.assertEqual(len(g.moves), 1)
        self.assertIsNone(g.moves[0]["by"])

    def test_best_of_three_alternates_who_starts(self):
        g, _ = make(2, match="3")
        starters = []
        while not g.finished:
            if g.phase == "play":
                starters.append(g.turn)
                play(g, [0, 6, 1, 6, 2, 6, 3])
            else:
                g.skip()
        # The starter wins every round and starters alternate: 1-1, so the third round decides it.
        self.assertEqual(len(starters), 3)
        self.assertEqual(starters, [starters[0], 1 - starters[0], starters[0]])
        self.assertEqual(sorted(g.wins), [1, 2])
        for viewer in [*g.player_ids, *SPECTATORS]:
            json.dumps(g.view_for(viewer))
        json.dumps(g.highlights())

    def test_two_nil_ends_early(self):
        g, _ = make(2, match="3")
        side = g.turn
        play(g, [0, 6, 1, 6, 2, 6, 3])  # round 1: the starter (side) wins
        g.skip()
        self.assertEqual(g.turn, 1 - side)
        play(g, [0, 1, 0, 1, 0, 1, 6, 1])  # round 2: the other side starts and side wins again
        self.assertEqual(g.winner, side)
        g.skip()
        self.assertTrue(g.finished)
        self.assertEqual(g.wins[side], 2)

    def test_view(self):
        g, _ = make(3)
        g.handle(g.mover, {"a": "drop", "col": 3})
        v = g.view_for("tv:screen")
        self.assertEqual(v["grid"][0][3], 1 - g.turn)
        self.assertIsNone(v["you"])
        self.assertEqual(v["last"]["col"], 3)
        self.assertEqual(sum(len(s) for s in v["sides"]), 3)


if __name__ == "__main__":
    unittest.main()
