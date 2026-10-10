"""Hot Potato Bomb: passing, the secret fuse, lives, the winner, input checks."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.bomb import ANSWER, SURVIVE, WIN, HotPotatoBomb, fold
from app.games.content import BOMB_PROMPTS

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=4, seed=1, **opts):
    clock = Clock()
    g = HotPotatoBomb(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=clock,
        options=opts or None,
    )
    g.start()
    return g, clock


class BombTests(unittest.TestCase):
    def test_answers_pass_it_round_the_circle(self):
        g, _ = make(4)
        self.assertEqual(g.phase, "pass")
        self.assertIn(g.prompt, BOMB_PROMPTS)
        seen = []
        for i in range(8):
            holder = g.holder
            seen.append(holder)
            g.handle(holder, {"a": "answer", "text": f"thing {i}"})
            self.assertEqual(g.holder, g.order[(g.order.index(holder) + 1) % 4])
        self.assertEqual(sorted(set(seen)), sorted(g.order))
        self.assertEqual(sum(g.round_scores.values()), 8 * ANSWER)
        self.assertEqual(len(g.view_for("p0")["answers"]), 8)

    def test_only_the_holder_and_only_new_answers(self):
        g, _ = make(3)
        other = next(p for p in g.order if p != g.holder)
        with self.assertRaises(GameError):
            g.handle(other, {"a": "answer", "text": "apple"})
        first = g.holder
        g.handle(first, {"a": "answer", "text": "  An   Apple! "})
        self.assertEqual(g.answers[-1]["text"], "An Apple!")
        for same in ("an apple", "AN-APPLE", "anapple"):
            with self.assertRaises(GameError):
                g.handle(g.holder, {"a": "answer", "text": same})
        for bad in (None, 7, "", "a", "!!", "x" * 31, "ap\x00ple", ["apple"]):
            with self.assertRaises(GameError):
                g.handle(g.holder, {"a": "answer", "text": bad})
        with self.assertRaises(GameError):
            g.handle(g.holder, {"a": "explode"})
        with self.assertRaises(GameError):
            g.handle("stranger", {"a": "answer", "text": "pear"})
        self.assertEqual(fold("Crème brûlée"), "cremebrulee")

    def test_the_fuse_is_secret_and_random(self):
        fuses = set()
        for seed in range(12):
            g, clock = make(4, seed)
            fuse = g.fuse_at - clock.t
            self.assertTrue(14.0 <= fuse <= 38.0)
            fuses.add(round(fuse, 3))
            for viewer in [*g.player_ids, *SPECTATORS]:
                view = g.view_for(viewer)
                self.assertIsNone(view["remaining"])
                self.assertNotIn("fuse", json.dumps(view))
                self.assertNotIn(str(round(g.fuse_at, 2)), json.dumps(view))
        self.assertGreater(len(fuses), 8)

    def test_boom_costs_a_life_and_the_rest_score(self):
        g, clock = make(4, lives="2")
        victim = g.holder
        clock.t += 13
        g.tick()
        self.assertEqual(g.phase, "pass")  # shorter than any fuse
        clock.t += 40
        g.tick()
        self.assertEqual(g.phase, "boom")
        self.assertEqual(g.lives[victim], 1)
        self.assertEqual(g.view_for("tv:screen")["boom"]["who"], victim)
        for p in g.order:
            self.assertEqual(g.round_scores[p], 0 if p == victim else SURVIVE)
        with self.assertRaises(GameError):
            g.handle(victim, {"a": "answer", "text": "too late"})
        old = g.prompt
        clock.t += 8
        g.tick()
        self.assertEqual((g.phase, g.round, g.holder), ("pass", 2, victim))  # it restarts with the victim
        self.assertNotEqual(g.prompt, old)
        self.assertEqual(g.answers, [])

    def test_out_of_lives_and_last_one_standing(self):
        g, _ = make(3, lives="1")
        first = g.holder
        g.advance()  # the host skips: it blows now
        self.assertEqual((g.phase, g.out), ("boom", [first]))
        g.advance()
        self.assertEqual(g.phase, "pass")
        self.assertNotEqual(g.holder, first)
        self.assertNotIn(first, [g._next(p) for p in g.order])
        second = g.holder
        g.advance()
        g.advance()
        self.assertTrue(g.finished)
        winner = next(p for p in g.order if p not in (first, second))
        view = g.view_for("au:fan")
        self.assertEqual(view["winner"], winner)
        self.assertEqual(g.round_scores[winner], 2 * SURVIVE + WIN)
        self.assertEqual(view["scores"], g.scores())

    def test_random_games_finish(self):
        for seed in range(20):
            rng = random.Random(seed)
            g, clock = make(rng.randint(2, 8), seed, lives=rng.choice(["1", "2", "3"]))
            n = 0
            for _ in range(4000):
                if g.finished:
                    break
                if g.phase == "pass" and rng.random() < 0.7:
                    n += 1
                    g.handle(g.holder, {"a": "answer", "text": f"answer {n}"})
                clock.t += rng.uniform(0.5, 4)
                g.tick()
            self.assertTrue(g.finished, seed)
            self.assertEqual(sum(v > 0 for v in g.lives.values()), 1)

    def test_prompts_do_not_repeat_within_a_room(self):
        decks: dict = {}
        seen = []
        for seed in range(6):
            g = HotPotatoBomb(
                [Player(id=f"p{i}", name=f"N{i}") for i in range(2)],
                rng=random.Random(seed),
                clock=Clock(),
                decks=decks,
                options={"lives": "5"},
            )
            g.start()
            while not g.finished:
                seen.append(g.prompt)
                g.advance()
                g.advance()
        self.assertEqual(len(seen), len(set(seen)))


if __name__ == "__main__":
    unittest.main()
