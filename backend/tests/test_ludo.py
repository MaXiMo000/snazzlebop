"""Ludo: seating and teams, getting out on a 6, moving, captures and safe squares, the exact count home,
bonus rolls, three 6s, the clock, the win, and that every view (players, TV, audience) is the same
public board in every phase."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.ludo import HOME, SAFE, START, YARD, Ludo, colors_for, square

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


class Dice(random.Random):
    """Rolls the given values in order (the seating shuffle still uses a real seed)."""

    def __init__(self, rolls):
        super().__init__(1)
        self.rolls = list(rolls)

    def randint(self, a, b):
        return self.rolls.pop(0)


def make(n=2, rolls=(), **opts):
    clock = Clock()
    g = Ludo(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=Dice(rolls),
        clock=clock,
        options=opts or None,
    )
    g.start()
    return g, clock


def act(g, a, **kw):
    g.handle(g.current, {"a": a, **kw})


class SeatingTests(unittest.TestCase):
    def test_colours_and_teams(self):
        self.assertEqual(colors_for(2), ("red", "yellow"))  # opposite corners
        self.assertEqual(colors_for(3), ("red", "green", "yellow"))
        self.assertEqual(len(colors_for(4)), 4)
        self.assertEqual([len(colors_for(n)) for n in (5, 6, 7, 8)], [3, 3, 4, 4])
        for n in range(2, 9):
            g, _ = make(n)
            sizes = sorted(len(m) for m in g.members.values())
            self.assertEqual(sum(sizes), n)
            self.assertLessEqual(sizes[-1] - sizes[0], 1)
            self.assertLessEqual(sizes[-1], 2)

    def test_teammates_take_turns_rolling(self):
        g, _ = make(6, rolls=[1, 1, 1, 1, 1, 1, 1])
        red = g.members["red"]
        self.assertEqual(g.color, "red")
        first = g.current
        for _ in range(3):  # nobody can move on a 1 from the yard: each colour passes
            act(g, "roll")
        self.assertEqual(g.color, "red")
        self.assertEqual({first, g.current}, set(red))

    def test_board_geometry(self):
        self.assertEqual(square("green", 0), 13)
        self.assertEqual(square("red", 51), None)
        self.assertEqual(square("blue", 13), 0)  # wraps round
        self.assertTrue(all(START[c] in SAFE for c in START))


class MoveTests(unittest.TestCase):
    def test_a_six_gets_out_and_rolls_again(self):
        g, _ = make(2, rolls=[3, 6, 4])
        act(g, "roll")  # 3: stuck in the yard, turn passes
        self.assertEqual(g.color, "yellow")
        act(g, "roll")  # 6: out (auto: every yard token is the same move)
        self.assertEqual(g.tokens["yellow"].count(0), 1)
        self.assertEqual(g.color, "yellow")  # bonus roll
        act(g, "roll")  # 4: the only token out moves (the others can't)
        self.assertEqual(sorted(g.tokens["yellow"]), [YARD, YARD, YARD, 4])
        self.assertEqual(g.color, "red")

    def test_choosing_a_token(self):
        g, _ = make(2, rolls=[6])
        g.tokens["red"] = [5, YARD, YARD, YARD]
        act(g, "roll")
        self.assertEqual(g.rolled, 6)  # out, or move the 5: a real choice
        self.assertEqual(g.view_for("p0")["movable"], [0, 1, 2, 3])
        with self.assertRaises(GameError):
            g.handle(g.members["yellow"][0], {"a": "move", "token": 0})
        for bad in (9, "1", True, None):
            with self.assertRaises(GameError):
                act(g, "move", token=bad)
        act(g, "move", token=0)
        self.assertEqual(g.tokens["red"][0], 11)
        with self.assertRaises(GameError):
            act(g, "move", token=0)  # roll first

    def test_exact_count_home(self):
        g, _ = make(2, rolls=[5, 3, 2])
        g.tokens["red"] = [53, HOME, HOME, HOME]
        act(g, "roll")  # 5 overshoots: no move
        self.assertEqual(g.tokens["red"][0], 53)
        g.turn = 0
        act(g, "roll")  # 3: home, wins
        self.assertTrue(g.finished)
        self.assertEqual(g.winner, "red")
        self.assertEqual(g.scores()[g.members["red"][0]], 100 + 500)

    def test_capture_and_safe_squares(self):
        g, _ = make(2, rolls=[4, 4])
        g.tokens["red"] = [10, YARD, YARD, YARD]
        g.tokens["yellow"] = [(14 - 26) % 52, YARD, YARD, YARD]  # on red's square 14
        act(g, "roll")
        self.assertEqual(g.tokens["yellow"][0], YARD)
        self.assertEqual(g.color, "red")  # capture = roll again
        self.assertEqual(g.points["red"], 50)
        # A rival on a star (square 21) is safe.
        g.tokens["red"] = [17, YARD, YARD, YARD]
        g.tokens["yellow"] = [(21 - 26) % 52, YARD, YARD, YARD]
        act(g, "roll")
        self.assertEqual(g.tokens["yellow"][0], (21 - 26) % 52)
        self.assertEqual(g.tokens["red"][0], 21)

    def test_a_stack_of_rivals_all_go_home(self):
        g, _ = make(2, rolls=[2])
        g.tokens["red"] = [3, YARD, YARD, YARD]
        here = (5 - 26) % 52
        g.tokens["yellow"] = [here, here, YARD, YARD]
        act(g, "roll")
        self.assertEqual(g.tokens["yellow"], [YARD] * 4)
        self.assertEqual(g.points["red"], 100)

    def test_three_sixes_lose_the_turn(self):
        g, _ = make(2, rolls=[6, 6, 6])
        g.tokens["red"] = [10, 20, 30, 40]
        act(g, "roll")
        act(g, "move", token=0)
        act(g, "roll")
        act(g, "move", token=0)
        self.assertEqual(g.color, "red")
        act(g, "roll")
        self.assertEqual(g.color, "yellow")
        self.assertEqual(g.tokens["red"][0], 22)  # the third 6 doesn't move
        self.assertEqual(g.log[-1]["type"], "bust")

    def test_the_clock_rolls_and_moves_the_furthest(self):
        g, clock = make(2, rolls=[2])
        g.tokens["red"] = [5, 30, YARD, YARD]
        clock.t = 21
        g.tick()
        self.assertEqual(g.tokens["red"][:2], [5, 32])
        self.assertEqual(g.color, "yellow")
        self.assertIsNotNone(g.deadline)


class ViewTests(unittest.TestCase):
    def ids(self, g):
        return [*g.player_ids, *SPECTATORS]

    def test_every_view_is_the_same_public_board_in_every_phase(self):
        g, _ = make(5, rolls=[6, 3, 4, 1] * 40, tokens="2")
        for _ in range(60):
            if g.finished:
                break
            views = [g.view_for(p) for p in self.ids(g)]
            plain = [
                json.dumps({k: v for k, v in view.items() if k != "you"}, sort_keys=True) for view in views
            ]
            self.assertEqual(len(set(plain)), 1)
            g.advance()
        g.tokens = {c: [HOME, 55] for c in g.colors}
        g.turn, g.rolled = 0, None
        g.rng.rolls = [1]
        act(g, "roll")
        self.assertEqual(g.phase, "final")
        for p in self.ids(g):
            v = g.view_for(p)
            self.assertEqual(v["winner"], g.colors[0])
            self.assertIsNone(v["turn"])
        self.assertEqual(g.view_for(g.player_ids[0])["you"], g.color_of[g.player_ids[0]])
        self.assertIsNone(g.view_for("tv:screen")["you"])
        self.assertTrue(g.highlights())
        with self.assertRaises(GameError):
            g.handle(g.player_ids[0], {"a": "roll"})
        g.advance()  # no-op once over
        self.assertTrue(g.finished)


if __name__ == "__main__":
    unittest.main()
