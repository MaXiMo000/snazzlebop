"""Hangman: setting a word, letters and solves, turns and clocks, the drawing, scores and secrecy."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.hangman import (
    LETTER_POINTS,
    MISSES,
    SETTER_POINTS,
    SOLVE_BONUS,
    SOLVE_POINTS,
    Hangman,
    clean_word,
)

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=3, seed=1, **opts):
    clock = Clock()
    g = Hangman(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=clock,
        options=opts or None,
    )
    g.start()
    return g, clock


def set_word(g, word="hot dog", hint=""):
    g.handle(g.setter, {"a": "set", "word": word, "hint": hint})


class HangmanTests(unittest.TestCase):
    def test_clean_word(self):
        self.assertEqual(clean_word("  Hot   Dog "), "hot dog")
        for bad in ("ab", "x1y", "hot-dog", "a b", "", None, "a" * 25):
            self.assertIsNone(clean_word(bad), bad)

    def test_every_suggestion_is_a_valid_word(self):
        from app.games.content import DRAW_WORDS

        for w in DRAW_WORDS:
            self.assertEqual(clean_word(w.replace("_", " ")), w.replace("_", " "))

    def test_setting(self):
        g, _ = make(3)
        self.assertEqual(len(g.view_for(g.setter)["suggestions"]), 3)
        other = g.guessers[0]
        self.assertEqual(g.view_for(other)["suggestions"], [])
        with self.assertRaises(GameError):
            g.handle(other, {"a": "set", "word": "apple"})
        with self.assertRaises(GameError):
            set_word(g, "apple", hint="an apple a day")  # the hint gives it away
        set_word(g, "hot dog", hint="Food")
        v = g.view_for(other)
        self.assertEqual(v["pattern"], [None, None, None, " ", None, None, None])
        self.assertEqual(v["hint"], "Food")
        self.assertIsNone(v["word"])
        self.assertEqual(g.view_for(g.setter)["word"], "hot dog")

    def test_letters_go_again_and_misses_pass_the_turn(self):
        g, _ = make(3)
        set_word(g, "hot dog")
        first = g.guesser
        g.handle(first, {"a": "letter", "letter": "O"})  # two of them
        self.assertEqual(g.scores()[first], 2 * LETTER_POINTS)
        self.assertEqual(g.guesser, first)  # right: go again
        with self.assertRaises(GameError):
            g.handle(first, {"a": "letter", "letter": "o"})  # used
        for bad in ("", "ab", "1", 5, "é"):
            with self.assertRaises(GameError):
                g.handle(first, {"a": "letter", "letter": bad})
        g.handle(first, {"a": "letter", "letter": "z"})
        self.assertEqual(g.misses, ["z"])
        self.assertNotEqual(g.guesser, first)
        with self.assertRaises(GameError):
            g.handle(first, {"a": "letter", "letter": "h"})  # not your turn now

    def test_solve_scores_the_hidden_letters(self):
        g, _ = make(3)
        set_word(g, "hot dog")
        p = g.guesser
        g.handle(p, {"a": "letter", "letter": "o"})
        g.handle(p, {"a": "solve", "word": "Hot Dog"})
        self.assertEqual(g.phase, "reveal")
        hidden = 4  # h t d g
        self.assertEqual(g.scores()[p], 2 * LETTER_POINTS + SOLVE_POINTS + SOLVE_BONUS * hidden)
        self.assertEqual(g.result["solver"], p)

    def test_six_misses_and_the_setter_scores(self):
        g, _ = make(2)
        set_word(g, "pumpkin")
        setter = g.setter
        for letter in "qwxyzv":
            g.handle(g.guesser, {"a": "letter", "letter": letter})
        self.assertEqual(g.phase, "reveal")
        self.assertEqual(len(g.misses), MISSES)
        self.assertEqual(g.scores()[setter], SETTER_POINTS)
        self.assertIsNone(g.result["solver"])

    def test_a_wrong_solve_is_a_miss(self):
        g, _ = make(3)
        set_word(g, "pumpkin")
        first = g.guesser
        g.handle(first, {"a": "solve", "word": "pancake"})
        self.assertEqual(len(g.misses), 1)
        self.assertNotEqual(g.guesser, first)

    def test_clocks_and_skip(self):
        g, clock = make(3)
        self.assertFalse(g.skip())
        clock.t += 40
        g.tick()  # the setter ran out of time: the first suggestion
        self.assertEqual(g.phase, "guess")
        self.assertEqual(g.word, g.suggestions[0])
        self.assertFalse(g.skip())
        first = g.guesser
        clock.t += 25
        g.tick()  # out of time: a miss and the next player's turn
        self.assertEqual(len(g.misses), 1)
        self.assertNotEqual(g.guesser, first)

    def test_everyone_sets_once_and_the_game_ends(self):
        g, clock = make(3)
        setters = []
        while not g.finished:
            if g.phase == "set":
                setters.append(g.setter)
            clock.t += 100
            g.tick()
        self.assertEqual(sorted(setters), sorted(g.player_ids))
        json.dumps(g.highlights())

    def test_secrecy(self):
        g, clock = make(3)
        set_word(g, "zebra crossing")
        while not g.finished:
            if g.phase == "guess" and g.word == "zebra crossing":
                for viewer in [*g.guessers, *SPECTATORS]:
                    blob = json.dumps(g.view_for(viewer))
                    self.assertNotIn("zebra", blob)
                    self.assertNotIn("crossing", blob)
                self.assertTrue(g.chat_blocked(g.setter, "it's ZEBRA-CROSSING"))
                self.assertIsNone(g.chat_blocked(g.guessers[0], "zebra crossing?"))
            if g.phase == "set":
                for viewer in [*g.guessers, *SPECTATORS]:
                    v = g.view_for(viewer)
                    self.assertEqual(v["suggestions"], [])
                    self.assertIsNone(v["word"])
            clock.t += 100
            g.tick()
        for viewer in [*g.player_ids, *SPECTATORS]:
            json.dumps(g.view_for(viewer))
        self.assertIn("zebra crossing", json.dumps(g.view_for("tv:screen")))


if __name__ == "__main__":
    unittest.main()
