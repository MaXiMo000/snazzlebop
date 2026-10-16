"""Five Dice: every box, the upper bonus, Five Dice bonuses and jokers, rolls and holds, the round clock."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.fivedice import BOXES, FIVE_BONUS, UPPER_BONUS, Card, FiveDice, box_score

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=2, seed=1, **opts):
    clock = Clock()
    g = FiveDice(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=clock,
        options=opts or None,
    )
    g.start()
    return g, clock


def rigged(g, pid, dice):
    """Roll once, then set the dice (the rolls themselves are random)."""
    g.handle(pid, {"a": "roll"})
    g.cards[pid].dice = list(dice)


class BoxTests(unittest.TestCase):
    def test_every_box(self):
        d = [3, 3, 3, 5, 5]
        self.assertEqual(box_score("threes", d), 9)
        self.assertEqual(box_score("fives", d), 10)
        self.assertEqual(box_score("ones", d), 0)
        self.assertEqual(box_score("three_kind", d), 19)
        self.assertEqual(box_score("four_kind", d), 0)
        self.assertEqual(box_score("full_house", d), 25)
        self.assertEqual(box_score("chance", d), 19)
        self.assertEqual(box_score("small_straight", [1, 2, 3, 4, 6]), 30)
        self.assertEqual(box_score("small_straight", [3, 4, 5, 6, 6]), 30)
        self.assertEqual(box_score("small_straight", [1, 2, 3, 5, 6]), 0)
        self.assertEqual(box_score("large_straight", [2, 3, 4, 5, 6]), 40)
        self.assertEqual(box_score("large_straight", [1, 2, 3, 4, 6]), 0)
        self.assertEqual(box_score("four_kind", [6, 6, 6, 6, 1]), 25)
        self.assertEqual(box_score("five_dice", [4] * 5), 50)
        self.assertEqual(box_score("full_house", [4] * 5), 0)  # five of a kind isn't a full house...
        self.assertEqual(box_score("full_house", [4] * 5, joker=True), 25)  # ...unless it's a joker

    def test_joker_rules(self):
        c = Card()
        c.rolls, c.dice = 1, [2] * 5
        self.assertIn("five_dice", c.allowed())  # first one: anywhere, including the 50 box
        c.boxes["five_dice"] = 50
        self.assertEqual(c.allowed(), {"twos": 10})  # the matching upper box is open: it must go there
        c.boxes["twos"] = 4
        joker = c.allowed()
        self.assertEqual(joker["full_house"], 25)
        self.assertEqual(joker["large_straight"], 40)
        self.assertNotIn("ones", joker)
        for b in ("three_kind", "four_kind", "full_house", "small_straight", "large_straight", "chance"):
            c.boxes[b] = 0
        self.assertEqual(set(c.allowed()), {"ones", "threes", "fours", "fives", "sixes"})
        self.assertTrue(all(v == 0 for v in c.allowed().values()))

    def test_upper_bonus(self):
        c = Card()
        c.boxes = {"ones": 3, "twos": 6, "threes": 9, "fours": 12, "fives": 15, "sixes": 18}
        self.assertEqual(c.upper, 63)
        self.assertEqual(c.total, 63 + UPPER_BONUS)
        c.boxes["sixes"] = 12
        self.assertEqual(c.total, 57)


class GameTests(unittest.TestCase):
    def test_rolls_holds_and_scoring(self):
        g, _ = make(2)
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "score", "box": "chance"})  # roll first
        g.handle("p0", {"a": "roll"})
        first = list(g.cards["p0"].dice)
        self.assertTrue(all(1 <= d <= 6 for d in first))
        for bad in (None, [True] * 4, [1, 0, 0, 0, 0], "all"):
            with self.assertRaises(GameError):
                g.handle("p0", {"a": "roll", "held": bad})
        g.handle("p0", {"a": "roll", "held": [True, True, False, False, False]})
        self.assertEqual(g.cards["p0"].dice[:2], first[:2])
        g.handle("p0", {"a": "roll", "held": [True] * 5})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "roll", "held": [False] * 5})  # three rolls a round
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "score", "box": "nonsense"})
        g.handle("p0", {"a": "score", "box": "chance"})
        self.assertEqual(g.scores()["p0"], sum(g.cards["p0"].dice))
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "roll"})  # done for this round
        self.assertEqual(g.round, 0)  # waiting for p1
        rigged(g, "p1", [1, 1, 1, 1, 1])
        g.handle("p1", {"a": "score", "box": "five_dice"})
        self.assertEqual((g.round, g.cards["p0"].rolls), (1, 0))  # everyone scored: next round
        with self.assertRaises(GameError):
            rigged(g, "p0", [6, 6, 6, 6, 6]) or g.handle("p0", {"a": "score", "box": "chance"})  # chance used

    def test_five_dice_bonus(self):
        g, _ = make(1)
        rigged(g, "p0", [5] * 5)
        g.handle("p0", {"a": "score", "box": "five_dice"})
        rigged(g, "p0", [5] * 5)
        g.handle("p0", {"a": "score", "box": "fives"})
        self.assertEqual(g.cards["p0"].bonus, FIVE_BONUS)
        self.assertEqual(g.scores()["p0"], 50 + 25 + FIVE_BONUS)

    def test_the_clock_fills_the_best_box_and_skip_is_refused(self):
        g, clock = make(3)
        rigged(g, "p0", [2, 3, 4, 5, 6])
        self.assertFalse(g.skip())
        clock.t += 75
        g.tick()
        self.assertEqual(g.round, 1)
        self.assertEqual(g.cards["p0"].boxes, {"large_straight": 40})
        self.assertEqual(len(g.cards["p1"].boxes), 1)  # rolled and scored for them
        self.assertTrue(all(not c.done for c in g.cards.values()))  # the new round wasn't touched

    def test_a_full_game(self):
        g, clock = make(3, card="13")
        while not g.finished:
            clock.t += 75
            g.tick()
        for c in g.cards.values():
            self.assertEqual(set(c.boxes), set(BOXES))
            self.assertEqual(g.scores()[next(p for p, x in g.cards.items() if x is c)], c.total)
        for viewer in [*g.player_ids, *SPECTATORS]:
            json.dumps(g.view_for(viewer))
        self.assertIsNone(g.view_for("tv:screen")["you"])
        json.dumps(g.highlights())

    def test_quick_card(self):
        g, clock = make(1, card="7")
        while not g.finished:
            clock.t += 75
            g.tick()
        self.assertEqual(len(g.cards["p0"].boxes), 7)

    def test_spectators_cannot_play(self):
        g, _ = make(1)
        for pid in SPECTATORS:
            with self.assertRaises(GameError):
                g.handle(pid, {"a": "roll"})


if __name__ == "__main__":
    unittest.main()
