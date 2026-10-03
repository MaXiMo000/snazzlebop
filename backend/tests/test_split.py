"""Split or Steal: payoffs, secrecy, pairing, byes, canned lines."""

from __future__ import annotations

import random
import unittest
from collections import Counter

from app.games import GameError, Player
from app.games.split import BYE_POINTS, ROUNDS, SplitOrSteal

SPECTATORS = ("tv:screen", "au:fan")


def make(n, seed=1):
    g = SplitOrSteal([Player(id=f"p{i}", name=f"N{i}") for i in range(n)], rng=random.Random(seed))
    g.start()
    return g


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
        for _ in range(ROUNDS):
            byes.append(g.bye)
            self.assertIsNone(g.partner(g.bye))
            with self.assertRaises(GameError):
                g.handle(g.bye, {"a": "choose", "choice": "split"})
            g.advance()
            g.advance()
        self.assertEqual(len(set(byes)), 5)  # five rounds, five different people sit out
        self.assertTrue(g.finished)
        self.assertTrue(all(g.scores()[p] >= BYE_POINTS for p in g.player_ids))  # silence = split, plus a bye

    def test_rematches_are_avoided_while_fresh_pairs_exist(self):
        g = make(6, seed=3)
        seen = Counter()
        for _ in range(ROUNDS):
            for pair in g.pairs:
                seen[frozenset(pair)] += 1
            g.advance()
            g.advance()
        self.assertEqual(max(seen.values()), 1)  # 6 players, 5 rounds: everyone meets everyone once

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


if __name__ == "__main__":
    unittest.main()
