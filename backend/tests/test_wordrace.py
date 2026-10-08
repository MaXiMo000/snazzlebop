"""Word Race: Wordle colours (duplicates!), the word list, hard mode, scoring, rounds, secrecy."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.content import WORD_ANSWERS, WORD_GUESSES, WORD_STEMS
from app.games.wordrace import WordRace, hard_mode_problem, is_word, mark

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=3, seed=1, **opts):
    clock = Clock()
    g = WordRace(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=clock,
        options=opts or None,
    )
    g.start()
    return g, clock


def wrong(g):
    """A valid guess that isn't the answer."""
    return next(w for w in ("CRANE", "SLATE", "PIZZA", "MOUSE") if w != g.answer)


class MarkTests(unittest.TestCase):
    def test_greens_yellows_greys(self):
        self.assertEqual(mark("CRANE", "CRANE"), "ggggg")
        self.assertEqual(mark("NACRE", "CRANE"), "yyyyg")
        self.assertEqual(mark("BLOWN", "CRANE"), "xxxxy")

    def test_duplicate_letters_follow_the_original(self):
        # Two Es guessed, one in the answer: only the first unmatched E is yellow.
        self.assertEqual(mark("GEESE", "THEME"), "xxgxg")
        self.assertEqual(mark("EERIE", "THEME"), "yxxxg")
        # One spare E: the leftmost E is yellow, the second grey.
        self.assertEqual(mark("SPEED", "ABIDE"), "xxyxy")
        self.assertEqual(mark("LLAMA", "HELLO"), "yyxxx")

    def test_word_list(self):
        self.assertTrue(all(len(w) == 5 and w.isalpha() and w.isupper() for w in WORD_ANSWERS))
        self.assertEqual(len(WORD_ANSWERS), len(set(WORD_ANSWERS)))
        self.assertTrue(all(len(w) == 4 for w in WORD_STEMS))
        self.assertTrue(all(len(w) == 5 for w in WORD_GUESSES))
        for w in ("CRANE", "ADIEU", "PIZZA", "BOOKS", "PLAYS"):
            self.assertTrue(is_word(w), w)
        for w in ("ASDFG", "ZZZZZ", "BOOKX", "CRANES"):
            self.assertFalse(is_word(w), w)

    def test_hard_mode_rules(self):
        history = [("CRANE", mark("CRANE", "CRUST"))]  # C, R green; nothing else
        self.assertIsNone(hard_mode_problem("CRUST", history))
        self.assertEqual(hard_mode_problem("TRUCK", history), "Letter 1 must be C")
        history = [("STARE", mark("STARE", "TRAIN"))]  # T, A, R yellow
        self.assertEqual(hard_mode_problem("PLAIN", history), "Your guess must contain T")


class GameTests(unittest.TestCase):
    def test_scoring_and_bonuses(self):
        g, _ = make(3)
        p0, p1, p2 = g.player_ids
        g.handle(p0, {"a": "guess", "word": g.answer})  # 1 guess, first: 600 + 100
        g.handle(p1, {"a": "guess", "word": wrong(g)})
        g.handle(p1, {"a": "guess", "word": g.answer.lower()})  # 2 guesses, second: 500 + 50
        self.assertEqual(g.gained[p0], 700)
        self.assertEqual(g.gained[p1], 550)
        self.assertEqual(g.phase, "play")
        for _ in range(6):
            g.handle(p2, {"a": "guess", "word": wrong(g)})
        self.assertEqual(g.phase, "reveal")  # everyone finished: reveal straight away
        self.assertEqual(g.scores(), {p0: 700, p1: 550, p2: 0})
        with self.assertRaises(GameError):
            g.handle(p2, {"a": "guess", "word": wrong(g)})

    def test_bad_guesses_are_refused_without_costing_a_try(self):
        g, _ = make(2)
        p = g.player_ids[0]
        for bad in ("ASDFG", "TOOLONG", "AB1DE", 12345, None, "ÉCLAT"):
            with self.assertRaises(GameError):
                g.handle(p, {"a": "guess", "word": bad})
        self.assertEqual(g.board[p], [])

    def test_hard_mode_is_enforced(self):
        g, _ = make(2, mode="hard")
        p = g.player_ids[0]
        g.answer = "CRUST"
        g.handle(p, {"a": "guess", "word": "CRANE"})
        with self.assertRaises(GameError):
            g.handle(p, {"a": "guess", "word": "TRUCK"})
        g.handle(p, {"a": "guess", "word": "CRUST"})
        self.assertIn(p, g.solved)

    def test_rounds_deal_fresh_words_and_finish(self):
        g, clock = make(2, rounds="3")
        seen = []
        for _ in range(3):
            seen.append(g.answer)
            g.advance()  # time up -> reveal
            v = g.view_for(g.player_ids[0])
            self.assertEqual(v["answer"], g.answer)
            g.advance()  # reveal -> next round / final
        self.assertTrue(g.finished)
        self.assertEqual(len(set(seen)), 3)
        v = g.view_for("tv:screen")
        self.assertEqual((v["phase"], len(v["history"])), ("final", 3))
        self.assertEqual(g.highlights()[-1]["title"], "Stumper")

    def test_letters_and_answer_stay_secret(self):
        g, _ = make(3)
        p0, p1, _ = g.player_ids
        g.answer = "QUILT"
        g.handle(p0, {"a": "guess", "word": "PIZZA"})
        g.handle(p0, {"a": "guess", "word": "QUILT"})
        for viewer in [p1, *SPECTATORS]:
            v = g.view_for(viewer)
            blob = json.dumps(v)
            self.assertNotIn("QUILT", blob)
            self.assertNotIn("PIZZA", blob)
            self.assertEqual([r["word"] for r in v["boards"][p0]], [None, None])
            self.assertEqual(v["boards"][p0][1]["marks"], "ggggg")  # colours are public
            self.assertIsNone(v["answer"])
            self.assertNotIn(p0, v["gained"])
        own = g.view_for(p0)
        self.assertEqual([r["word"] for r in own["boards"][p0]], ["PIZZA", "QUILT"])
        self.assertIsNone(own["answer"])
        g.advance()  # reveal: the book opens for everyone
        v = g.view_for("tv:screen")
        self.assertEqual(v["answer"], "QUILT")
        self.assertEqual([r["word"] for r in v["boards"][p0]], ["PIZZA", "QUILT"])


if __name__ == "__main__":
    unittest.main()
