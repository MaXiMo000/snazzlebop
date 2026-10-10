"""Snakes and Ladders: moves, ladders and snakes, sixes, the exact finish, turns and timers."""

from __future__ import annotations

import random
import unittest

from app.games import GameError, Player
from app.games.snakes import JUMPS, LADDERS, LAST, PER_SQUARE, SNAKES, WIN, SnakesAndLadders


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


class Dice:
    """A rigged die: the given rolls in order (the shuffle of seats still uses a real generator)."""

    def __init__(self, rolls):
        self.rolls = list(rolls)
        self.real = random.Random(1)

    def randint(self, a, b):
        return self.rolls.pop(0)

    def shuffle(self, x):
        self.real.shuffle(x)


def make(n=3, rolls=None, seed=1):
    clock = Clock()
    rng = Dice(rolls) if rolls is not None else random.Random(seed)
    g = SnakesAndLadders([Player(id=f"p{i}", name=f"N{i}") for i in range(n)], rng=rng, clock=clock)
    g.start()
    return g, clock


def roll(g, clock):
    clock.t += 2
    g.handle(g.current, {"a": "roll"})


class BoardTests(unittest.TestCase):
    def test_the_board_is_sane(self):
        self.assertTrue(all(a < b for a, b in LADDERS.items()))
        self.assertTrue(all(a > b for a, b in SNAKES.items()))
        self.assertFalse(set(LADDERS) & set(SNAKES))
        self.assertFalse(set(JUMPS) & set(JUMPS.values()))  # no chains: a jump never lands on another
        self.assertNotIn(LAST, JUMPS)
        self.assertTrue(all(1 <= s <= LAST for s in [*JUMPS, *JUMPS.values()]))


class PlayTests(unittest.TestCase):
    def test_moves_ladders_and_snakes(self):
        g, clock = make(2, [3, 2, 4, 6, 6])
        a, b = g.order
        roll(g, clock)
        self.assertEqual(g.pos[a], 3)
        self.assertEqual(g.last["via"], None)
        roll(g, clock)  # b lands on 2: the ladder to 38
        self.assertEqual(g.pos[b], 38)
        self.assertEqual((g.last["mid"], g.last["to"], g.last["via"]), (2, 38, "ladder"))
        roll(g, clock)  # a: 3 + 4 = 7, ladder to 14
        self.assertEqual(g.pos[a], 14)
        roll(g, clock)  # b: 38 + 6 = 44
        self.assertEqual(g.current, b)  # a six rolls again
        roll(g, clock)  # b: 44 + 6 = 50
        self.assertEqual((g.pos[b], g.current), (50, b))

    def test_snake(self):
        g, clock = make(2, [1])
        a = g.current
        g.pos[a] = 15
        roll(g, clock)  # 16: down to 6
        self.assertEqual((g.pos[a], g.last["via"]), (6, "snake"))
        self.assertEqual(g.stats[a]["snakes"], 1)

    def test_three_sixes_end_the_turn(self):
        g, clock = make(2, [6, 6, 6, 1])
        a, b = g.order
        for _ in range(3):
            self.assertEqual(g.current, a)
            roll(g, clock)
        self.assertEqual(g.current, b)
        self.assertEqual(g.pos[a], 18)

    def test_exact_roll_to_finish_and_scores(self):
        g, clock = make(3, [5, 1, 1, 3])
        a, b, c = g.order
        g.pos.update({a: 97, b: 40, c: 9})
        roll(g, clock)  # 97 + 5 is too much: stays
        self.assertEqual((g.pos[a], g.last["from"], g.last["to"]), (97, 97, 97))
        self.assertFalse(g.finished)
        roll(g, clock)
        roll(g, clock)
        roll(g, clock)  # a: 97 + 3 = 100
        self.assertTrue(g.finished)
        self.assertEqual(g.winner, a)
        self.assertEqual(g.round_scores, {a: WIN, b: 41 * PER_SQUARE, c: 10 * PER_SQUARE})
        view = g.view_for("tv:screen")
        self.assertEqual((view["phase"], view["winner"], view["scores"]), ("final", a, g.scores()))
        with self.assertRaises(GameError):
            g.handle(b, {"a": "roll"})

    def test_turns_input_and_the_landing_pause(self):
        g, clock = make(3, [2, 3, 4])
        other = next(p for p in g.order if p != g.current)
        with self.assertRaises(GameError):
            g.handle(other, {"a": "roll"})
        with self.assertRaises(GameError):
            g.handle(g.current, {"a": "move"})
        with self.assertRaises(GameError):
            g.handle("stranger", {"a": "roll"})
        g.handle(g.current, {"a": "roll"})
        with self.assertRaises(GameError):
            g.handle(g.current, {"a": "roll"})  # the last token is still walking
        clock.t += 1.3
        g.handle(g.current, {"a": "roll"})

    def test_the_clock_rolls_for_a_sleeper(self):
        g, clock = make(2, [4, 5])
        first = g.current
        clock.t += 16
        g.tick()
        self.assertEqual(g.pos[first], 4)
        self.assertNotEqual(g.current, first)
        g.advance()  # the host can roll for them too
        self.assertEqual(g.moves, 2)

    def test_random_games_finish_and_never_break_the_board(self):
        for seed in range(25):
            g, clock = make(random.Random(seed).randint(2, 8), seed=seed)
            for _ in range(5000):
                if g.finished:
                    break
                roll(g, clock)
                self.assertTrue(all(0 <= at <= LAST and at not in JUMPS for at in g.pos.values()))
            self.assertTrue(g.finished, seed)
            self.assertEqual(g.pos[g.winner], LAST)

    def test_everyone_sees_the_same_board(self):
        g, clock = make(4)
        roll(g, clock)
        views = [g.view_for(v) for v in [*g.player_ids, "tv:screen", "au:fan"]]
        self.assertTrue(all(v == views[0] for v in views))


if __name__ == "__main__":
    unittest.main()
