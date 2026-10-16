"""Letter Lists: letters, matching answers, the room's no votes, scoring, autosave, clocks, secrecy."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.content import LIST_CATEGORIES
from app.games.lists import LETTERS, PER_ROUND, POINTS, LetterLists, key, starts_with

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=3, seed=1, **opts):
    clock = Clock()
    g = LetterLists(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=clock,
        options=opts or None,
    )
    g.start()
    return g, clock


def fill(g, pid, words, done=True):
    words = (words + [""] * PER_ROUND)[:PER_ROUND]
    g.handle(pid, {"a": "answers", "answers": words, "done": done})


class HelperTests(unittest.TestCase):
    def test_key_and_letter(self):
        self.assertEqual(key("The Beatles!"), key("beatles"))
        self.assertEqual(key("Hot  Dog"), key("hotdog"))
        self.assertTrue(starts_with("the Bear", "B"))  # "the" doesn't count
        self.assertTrue(starts_with("  banana", "b"))
        self.assertFalse(starts_with("apple", "B"))
        self.assertFalse(starts_with("", "B"))
        self.assertNotIn("Q", LETTERS)
        self.assertGreater(len(LIST_CATEGORIES), 250)


class GameTests(unittest.TestCase):
    def test_scoring_unique_same_bad(self):
        g, _ = make(3)
        L = g.letter
        fill(g, "p0", [f"{L}aaa", f"{L}same", "zzz wrong letter", f"{L}one"])
        fill(g, "p1", [f"{L}bbb", f"{L}SAME!", "", f"{L}two"])
        self.assertEqual(g.phase, "write")
        fill(g, "p2", [f"{L}ccc"])
        self.assertEqual(g.phase, "review")
        g.advance()
        st = g.result["status"]
        self.assertEqual(st["p0"][:4], ["ok", "same", "bad", "ok"])
        self.assertEqual(st["p1"][:4], ["ok", "same", "bad", "ok"])
        self.assertEqual(g.result["gains"], {"p0": 2 * POINTS, "p1": 2 * POINTS, "p2": POINTS})

    def test_the_room_can_reject_an_answer(self):
        g, _ = make(3)
        L = g.letter
        fill(g, "p0", [f"{L}nonsense"])
        fill(g, "p1", [])
        fill(g, "p2", [])
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "nope", "who": "p0", "i": 0})  # not your own
        with self.assertRaises(GameError):
            g.handle("p1", {"a": "nope", "who": "p0", "i": 1})  # nothing there
        g.handle("p1", {"a": "nope", "who": "p0", "i": 0})
        self.assertEqual(g.view_for("tv:screen")["nopes"], {"p0:0": 1})
        self.assertEqual(g.view_for("p1")["you"]["noped"], ["p0:0"])
        g.handle("p2", {"a": "nope", "who": "p0", "i": 0})  # 2 of the 2 others: out
        g.advance()
        self.assertEqual(g.result["status"]["p0"][0], "nope")
        self.assertEqual(g.result["gains"]["p0"], 0)

    def test_one_no_of_two_others_is_not_enough(self):
        g, _ = make(3)
        fill(g, "p0", [f"{g.letter}fine"])
        fill(g, "p1", [])
        fill(g, "p2", [])
        g.handle("p1", {"a": "nope", "who": "p0", "i": 0})
        g.handle("p2", {"a": "nope", "who": "p0", "i": 0})
        g.handle("p2", {"a": "nope", "who": "p0", "i": 0})  # changed their mind
        g.advance()
        self.assertEqual(g.result["status"]["p0"][0], "ok")

    def test_autosave_counts_when_the_clock_runs_out(self):
        g, clock = make(2, writing="60")
        fill(g, "p0", [f"{g.letter}saved"], done=False)
        self.assertFalse(g.skip())  # the host can't cut the writing short
        clock.t += 60
        g.tick()
        self.assertEqual(g.phase, "review")
        g.skip()
        self.assertEqual(g.result["gains"]["p0"], POINTS)

    def test_bad_input(self):
        g, _ = make(2)
        for bad in (
            {"a": "answers", "answers": ["x"] * 5, "done": True},
            {"a": "answers", "answers": ["x" * 31] + [""] * 5, "done": True},
            {"a": "answers", "answers": [1] + [""] * 5, "done": True},
            {"a": "answers", "answers": ["\x00"] + [""] * 5, "done": True},
            {"a": "answers", "answers": [""] * 6, "done": "yes"},
            {"a": "nope", "who": "p1", "i": 0},  # not reviewing yet
            {"a": "huh"},
        ):
            with self.assertRaises(GameError, msg=bad):
                g.handle("p0", bad)
        with self.assertRaises(GameError):
            g.handle("tv:screen", {"a": "answers", "answers": [""] * 6, "done": True})

    def test_rounds_use_different_letters_and_categories(self):
        g, clock = make(2, lists="5")
        seen, cats = [], []
        while not g.finished:
            if g.phase == "write":
                seen.append(g.letter)
                cats += g.categories
            clock.t += 200
            g.tick()
        self.assertEqual(len(seen), 5)
        self.assertEqual(len(set(seen)), 5)
        self.assertEqual(len(set(cats)), 5 * PER_ROUND)
        json.dumps(g.highlights())

    def test_secrecy_every_phase(self):
        g, clock = make(3)
        while not g.finished:
            if g.phase == "write":
                fill(g, "p0", [f"{g.letter}secretword{g.round}"], done=False)
                for viewer in ["p1", "p2", *SPECTATORS]:
                    v = g.view_for(viewer)
                    self.assertIsNone(v["answers"])
                    self.assertNotIn(f"secretword{g.round}", json.dumps(v))
                self.assertIn(f"secretword{g.round}", json.dumps(g.view_for("p0")))
                self.assertTrue(g.chat_muted("p1"))
            else:
                for viewer in [*g.player_ids, *SPECTATORS]:
                    self.assertIn(f"secretword{g.round}", json.dumps(g.view_for(viewer)))
            clock.t += 200
            g.tick()
        for viewer in [*g.player_ids, *SPECTATORS]:
            json.dumps(g.view_for(viewer))
        self.assertIsNone(g.view_for("tv:screen")["you"])

    def test_great_minds_highlight(self):
        g, clock = make(2, lists="2")
        fill(g, "p0", [f"{g.letter}twin"])
        fill(g, "p1", [f"{g.letter}Twin"])
        while not g.finished:
            clock.t += 200
            g.tick()
        titles = [h["title"] for h in g.highlights()]
        self.assertIn("Great minds", titles)


if __name__ == "__main__":
    unittest.main()
