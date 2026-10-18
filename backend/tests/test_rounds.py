"""The host can pick how many rounds a game runs: every length plays through to the end."""

from __future__ import annotations

import random
import unittest

from app.games import REGISTRY, Player

LENGTHS = {
    "chicken": "runs",
    "split": "deals",
    "wits": "bets",
    "roulette": "spins",
    "lonely": "picks",
    "frenemy": "rankings",
    "telepathy": "minds",
    "price": "items",
}


class RoundsTests(unittest.TestCase):
    def test_every_length_plays_to_the_end(self):
        for game_id, key in LENGTHS.items():
            cls = REGISTRY[game_id]
            for value in cls.OPTIONS[key]:
                with self.subTest(game=game_id, rounds=value):
                    players = [Player(id=f"p{i}", name=f"N{i}") for i in range(4)]
                    g = cls(players, rng=random.Random(3), clock=lambda: 0.0, options={key: value})
                    g.start()
                    self.assertEqual(g.view_for("p0")["rounds"], int(value))
                    seen = set()
                    for _ in range(400):
                        if g.finished:
                            break
                        seen.add(g.round)
                        g.advance()
                    self.assertTrue(g.finished)
                    self.assertEqual(len(seen), int(value))
