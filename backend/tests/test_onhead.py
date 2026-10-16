"""On Your Head: who sees the word, marking words (and double taps), forehead mode, clocks and points."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.onhead import CLUE_POINTS, GUESS_POINTS, OnYourHead


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=3, seed=1, **opts):
    clock = Clock()
    g = OnYourHead(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=clock,
        options=opts or None,
    )
    g.start()
    return g, clock


def go(g, clock):
    clock.t += 10
    g.tick()
    assert g.phase == "play"


class OnHeadTests(unittest.TestCase):
    def test_who_sees_the_word(self):
        g, clock = make(3)
        self.assertEqual(g.phase, "ready")
        for pid in [*g.player_ids, "tv:screen", "au:fan"]:
            self.assertIsNone(g.view_for(pid)["word"])  # nothing before the turn starts
        go(g, clock)
        word = g.words[0]
        guesser = g.guesser
        for pid in g.player_ids:
            self.assertEqual(g.view_for(pid)["word"], None if pid == guesser else word)
        self.assertIsNone(g.view_for("tv:screen")["word"])  # the guesser can see the TV
        self.assertEqual(g.view_for("au:fan")["word"], word)
        self.assertNotIn(word, json.dumps(g.view_for(guesser)))
        self.assertNotIn(word, json.dumps(g.view_for("tv:screen")))
        g.handle(guesser, {"a": "forehead", "on": True})
        self.assertEqual(g.view_for(guesser)["word"], word)  # the phone faces the room now

    def test_marking_points_and_double_taps(self):
        g, clock = make(3)
        go(g, clock)
        guesser = g.guesser
        a, b = [p for p in g.player_ids if p != guesser]
        g.handle(a, {"a": "got", "n": 0})
        g.handle(b, {"a": "got", "n": 0})  # a second tap on the same word is ignored
        self.assertEqual(g.n, 1)
        self.assertEqual(g.scores(), {guesser: GUESS_POINTS, a: CLUE_POINTS, b: CLUE_POINTS})
        g.handle(b, {"a": "pass", "n": 1})
        self.assertEqual((g.n, g.passed), (2, [g.words[1]]))
        with self.assertRaises(GameError):
            g.handle(guesser, {"a": "got", "n": 2})  # not without forehead mode
        g.handle(guesser, {"a": "forehead", "on": True})
        g.handle(guesser, {"a": "got", "n": 2})
        self.assertEqual(len(g.got), 2)
        for bad in ({"a": "got", "n": 99}, {"a": "got", "n": True}, {"a": "got"}, {"a": "nope"}):
            with self.assertRaises(GameError):
                g.handle(a, bad)
        with self.assertRaises(GameError):
            g.handle(a, {"a": "forehead", "on": True})  # only the guesser

    def test_turn_clock_rotation_and_skip(self):
        g, clock = make(3, seconds="45")
        go(g, clock)
        self.assertFalse(g.skip())  # a running turn can't be cut short
        clock.t += 45
        g.tick()
        self.assertEqual(g.phase, "result")
        self.assertTrue(g.skip())
        self.assertEqual((g.phase, g.round), ("ready", 1))
        guessers = []
        g2, c2 = make(3, goes="2")
        while not g2.finished:
            if g2.phase == "play":
                guessers.append(g2.guesser)
            c2.t += 100
            g2.tick()
        self.assertEqual(sorted(guessers), sorted(g2.player_ids * 2))
        for pid in [*g2.player_ids, "tv:screen"]:
            json.dumps(g2.view_for(pid))
        json.dumps(g2.highlights())

    def test_chat_is_muted_during_a_turn(self):
        g, clock = make(2)
        self.assertFalse(g.chat_muted("p0"))
        go(g, clock)
        self.assertTrue(g.chat_muted("p0"))

    def test_words_dont_repeat_across_turns(self):
        g, clock = make(3)
        seen = []
        while not g.finished:
            if g.phase == "play":
                seen += g.words
            clock.t += 100
            g.tick()
        self.assertEqual(len(seen), len(set(seen)))


if __name__ == "__main__":
    unittest.main()
