"""Crossword Race: grid construction is always a legal crossword; answers stay secret until solved."""

from __future__ import annotations

import random
import unittest

from app.games import GameError, Player
from app.games.content import CROSSWORD_ENTRIES
from app.games.crossword import CrosswordRace, build_grid

TV = "tv:screen"


def runs(cells: dict[tuple[int, int], str]) -> set[tuple[str, int, int, str]]:
    """Every maximal across/down run of 2+ letters as (word, row, col, dir)."""
    out = set()
    for r, c in cells:
        for dr, dc, d in ((0, 1, "across"), (1, 0, "down")):
            if (r - dr, c - dc) in cells:
                continue  # not the start of a run
            word = ""
            rr, cc = r, c
            while (rr, cc) in cells:
                word += cells[(rr, cc)]
                rr, cc = rr + dr, cc + dc
            if len(word) >= 2:
                out.add((word, r, c, d))
    return out


class GridTests(unittest.TestCase):
    def test_every_grid_is_a_legal_connected_crossword(self):
        for seed in range(200):
            rng = random.Random(seed)
            words = rng.sample(CROSSWORD_ENTRIES, 40)
            placed = build_grid(words, rng)
            self.assertGreaterEqual(len(placed), 6, f"seed {seed}: only {len(placed)} words")
            cells: dict[tuple[int, int], str] = {}
            for p in placed:
                for k, ch in enumerate(p["word"]):
                    rc = (p["row"] + k * (p["dir"] == "down"), p["col"] + k * (p["dir"] == "across"))
                    self.assertEqual(cells.setdefault(rc, ch), ch, f"seed {seed}: clash at {rc}")
            # No accidental words: the letter runs on the grid are exactly the placed words.
            self.assertEqual(runs(cells), {(p["word"], p["row"], p["col"], p["dir"]) for p in placed}, seed)
            rows = [rc[0] for rc in cells]
            cols = [rc[1] for rc in cells]
            self.assertEqual(min(rows), 0)
            self.assertEqual(min(cols), 0)
            self.assertLessEqual(max(rows), 14)
            self.assertLessEqual(max(cols), 14)
            # Connected: every word crosses the rest of the grid.
            seen, todo = set(), [next(iter(cells))]
            while todo:
                r, c = todo.pop()
                if (r, c) in seen or (r, c) not in cells:
                    continue
                seen.add((r, c))
                todo += [(r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)]
            self.assertEqual(seen, set(cells), seed)


def make(n=3, seed=1):
    clock = [1000.0]
    players = [Player(id=f"p{i}", name=f"N{i}") for i in range(n)]
    g = CrosswordRace(players, rng=random.Random(seed), clock=lambda: clock[0])
    g.start()
    return g, [p.id for p in players], clock


class CrosswordTests(unittest.TestCase):
    def test_answers_are_secret_until_solved(self):
        g, ids, _ = make()
        first = g.clues[0]
        for viewer in [*ids, TV]:
            v = g.view_for(viewer)
            self.assertTrue(all("answer" not in c for c in v["clues"]))
            self.assertTrue(all(cell["letter"] is None for cell in v["cells"]))  # nothing revealed yet
        g.handle("p0", {"a": "guess", "clue": 0, "answer": first["word"].lower()})
        v = g.view_for("p1")
        solved = next(c for c in v["clues"] if c["id"] == 0)
        self.assertEqual((solved["answer"], solved["solved_by"]), (first["word"], "p0"))
        others = [c for c in v["clues"] if c["id"] != 0]
        self.assertTrue(all("answer" not in c for c in others))
        shown = {(c["row"], c["col"]): c["letter"] for c in v["cells"] if c["letter"]}
        self.assertEqual(len(shown), len(first["word"]))  # exactly that word's letters (crossings included)

    def test_scoring_first_solver_wrong_guess_lockout_and_validation(self):
        g, ids, clock = make()
        word = g.clues[1]["word"]
        with self.assertRaises(GameError):
            g.handle("p1", {"a": "guess", "clue": 1, "answer": "WRONGWORD"[: len(word)]})
        with self.assertRaises(GameError) as locked:
            g.handle("p1", {"a": "guess", "clue": 1, "answer": word})  # 2 s lockout after a miss
        self.assertEqual(locked.exception.code, "cooldown")
        clock[0] += 2.1
        g.handle("p1", {"a": "guess", "clue": 1, "answer": f" {word.lower()} "})
        self.assertEqual(g.scores()["p1"], 40 + 10 * len(word))
        with self.assertRaises(GameError):
            g.handle("p2", {"a": "guess", "clue": 1, "answer": word})  # already solved
        for bad in (
            {"clue": 99, "answer": "X"},
            {"clue": True, "answer": "X"},
            {"clue": 0, "answer": 5},
            {"clue": 0, "answer": "<script>"},
            {"clue": 0, "answer": "A" * 40},
        ):
            with self.assertRaises(GameError):
                g.handle("p2", {"a": "guess", **bad})

    def test_hints_reveal_letters_over_time_and_game_ends(self):
        g, ids, clock = make()
        clock[0] += 91
        g.tick()
        v = g.view_for(TV)
        self.assertEqual(v["hint_level"], 1)
        revealed = [c for c in v["cells"] if c["letter"]]
        self.assertGreaterEqual(len(revealed), len(g.clues) // 2)  # first letters (some shared)
        self.assertTrue(all("answer" not in c for c in v["clues"]))
        for i, c in enumerate(g.clues):
            g.handle(ids[i % 3], {"a": "guess", "clue": i, "answer": c["word"]})
        self.assertTrue(g.finished)
        self.assertTrue(all("answer" in c for c in g.view_for(TV)["clues"]))

    def test_time_runs_out_and_everything_is_revealed(self):
        g, ids, clock = make()
        clock[0] += 1000
        g.tick()
        self.assertTrue(g.finished)
        v = g.view_for(TV)
        self.assertTrue(all(c["letter"] for c in v["cells"]))
        self.assertTrue(all("answer" in c for c in v["clues"]))


if __name__ == "__main__":
    unittest.main()
