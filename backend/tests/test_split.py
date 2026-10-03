"""Split or Steal: payoffs, secrecy, pairing, byes, canned lines."""

from __future__ import annotations

import random
import unittest
from collections import Counter

from app.games import GameError, Player
from app.games.split import BYE_POINTS, GOLDEN_PER_PLAYER, ROUNDS, SplitOrSteal

SPECTATORS = ("tv:screen", "au:fan")


def make(n, seed=1):
    g = SplitOrSteal([Player(id=f"p{i}", name=f"N{i}") for i in range(n)], rng=random.Random(seed))
    g.start()
    g.advance()  # talk -> choose
    return g


def next_round(g):
    """From a round's choose phase to the next round's choose phase."""
    g.advance()  # reveal
    g.advance()  # next round's talk (or the end)
    if not g.finished:
        g.advance()  # choose


class SplitTests(unittest.TestCase):
    def test_payoffs(self):
        for a_choice, b_choice, want in (
            ("split", "split", "half"),
            ("steal", "split", "a"),
            ("split", "steal", "b"),
            ("steal", "steal", "none"),
        ):
            g = make(2)
            (a, b), pot = g.pairs[0], g.view_for("p0")["pairs"][0]["pot"]
            g.handle(a, {"a": "choose", "choice": a_choice})
            g.handle(b, {"a": "choose", "choice": b_choice})
            got = (g.scores()[a], g.scores()[b])
            expect = {"half": (pot // 2, pot // 2), "a": (pot, 0), "b": (0, pot), "none": (0, 0)}[want]
            self.assertEqual(got, expect, (a_choice, b_choice))

    def test_choices_are_secret_until_the_reveal(self):
        g = make(4)
        a, b = g.pairs[0]
        g.handle(a, {"a": "choose", "choice": "steal"})
        for viewer in (b, *(x for pair in g.pairs[1:] for x in pair), *SPECTATORS):
            view = g.view_for(viewer)
            self.assertNotIn("result", view)
            self.assertIsNone(view["you"]["choice"])
            self.assertNotIn("steal", str({k: v for k, v in view.items() if k not in ("lines", "record")}))
        self.assertEqual(g.view_for(a)["you"]["choice"], "steal")
        self.assertEqual(g.view_for(b)["locked"], [a])
        self.assertEqual(g.view_for(b)["record"][a], {"split": 0, "steal": 0})  # record moves at the reveal

    def test_odd_tables_rotate_the_bye(self):
        g = make(5)
        byes = []
        for _ in range(ROUNDS - 1):  # the paired rounds (the last one is the Golden Pot)
            byes.append(g.bye)
            self.assertIsNone(g.partner(g.bye))
            with self.assertRaises(GameError):
                g.handle(g.bye, {"a": "choose", "choice": "split"})
            next_round(g)
        self.assertEqual(len(set(byes)), ROUNDS - 1)  # a different person sits out every paired round
        self.assertTrue(g.golden)
        self.assertIsNone(g.bye)
        next_round(g)
        self.assertTrue(g.finished)
        self.assertTrue(all(g.scores()[p] >= BYE_POINTS for p in g.player_ids))  # silence = split, plus a bye

    def test_rematches_are_avoided_while_fresh_pairs_exist(self):
        g = make(6, seed=3)
        seen = Counter()
        for _ in range(ROUNDS):
            for pair in g.pairs:
                seen[frozenset(pair)] += 1
            next_round(g)
        self.assertEqual(max(seen.values()), 1)  # 6 players, 4 paired rounds: never the same pair twice

    def test_canned_lines_once_per_round_and_validated(self):
        g = make(2)
        g.handle("p0", {"a": "say", "line": 0})
        self.assertEqual(g.view_for("tv:x")["said"], {"p0": "I'm splitting 🤝"})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "say", "line": 1})
        for bad in (-1, 99, "0", True):
            with self.assertRaises(GameError):
                g.handle("p1", {"a": "say", "line": bad})
        with self.assertRaises(GameError):
            g.handle("p1", {"a": "choose", "choice": "maybe"})


class GoldenAndTalkTests(unittest.TestCase):
    def to_golden(self, n):
        g = make(n)
        for _ in range(ROUNDS - 1):
            next_round(g)
        self.assertTrue(g.golden)
        return g

    def golden(self, choices):
        g = self.to_golden(len(choices))
        before = g.scores()
        for i, c in enumerate(choices):
            g.handle(f"p{i}", {"a": "choose", "choice": c})
        self.assertEqual(g.phase, "reveal")
        return g, {p: g.scores()[p] - before[p] for p in g.player_ids}

    def test_golden_pot_all_split_shares_it(self):
        _, gain = self.golden(["split"] * 4)
        self.assertEqual(set(gain.values()), {GOLDEN_PER_PLAYER})

    def test_golden_pot_one_thief_takes_it_all(self):
        _, gain = self.golden(["split", "steal", "split"])
        self.assertEqual(gain, {"p0": 0, "p1": 3 * GOLDEN_PER_PLAYER, "p2": 0})

    def test_golden_pot_two_thieves_get_nothing(self):
        g, gain = self.golden(["steal", "steal", "split", "split"])
        self.assertEqual(set(gain.values()), {0})
        self.assertEqual(g.result["golden"]["choices"]["p0"], "steal")

    def test_golden_choices_stay_secret_and_odd_tables_play_everyone(self):
        g = self.to_golden(5)
        g.handle("p0", {"a": "choose", "choice": "steal"})
        for viewer in ("p1", "p4", *SPECTATORS):
            view = g.view_for(viewer)
            self.assertNotIn("result", view)
            self.assertIsNone(view["you"]["choice"])
            self.assertTrue(view["golden"])
            self.assertEqual(view["golden_pot"], 5 * GOLDEN_PER_PLAYER)
        for i in range(1, 5):
            g.handle(f"p{i}", {"a": "choose", "choice": "split"})  # nobody sits out the Golden Pot
        self.assertEqual(g.result["golden"]["gain"]["p0"], 5 * GOLDEN_PER_PLAYER)

    def test_talk_first_then_choose(self):
        g = SplitOrSteal([Player(id=f"p{i}", name=f"N{i}") for i in range(2)], rng=random.Random(1))
        g.start()
        self.assertEqual(g.phase, "talk")
        g.handle("p0", {"a": "say", "line": 2})  # lines are fine while talking
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "choose", "choice": "split"})
        g.advance()
        g.handle("p0", {"a": "choose", "choice": "split"})


if __name__ == "__main__":
    unittest.main()
