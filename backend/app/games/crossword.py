"""Crossword Race: a fresh crossword every game, solved against the clock and each other.

The grid is built from the content pool each game (longest words first, every word crossing the
grid on a shared letter, no accidental letter runs, at most 15x15). Players type answers; the first
correct solver of a word scores 40 + 10 per letter. A wrong guess locks you out for 2 seconds, so
brute force doesn't pay. Hints reveal letters at 90 s and 160 s.

Secrecy: views carry lengths, positions, numbers and clues, never an answer until it's solved (or
the game ends). Revealed cells only ever come from solved words and hints.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from .base import Game, GameError, as_int
from .content import CROSSWORD_ENTRIES

SIZE = 15
MAX_WORDS = 11
MIN_WORDS = 6
LOCKOUT = 2.0
HINT_TIMES = (90.0, 160.0)

Cell = tuple[int, int]


def _cells(word: str, r: int, c: int, d: str) -> list[Cell]:
    dr, dc = (0, 1) if d == "across" else (1, 0)
    return [(r + k * dr, c + k * dc) for k in range(len(word))]


def _fits(grid: dict[Cell, tuple[str, set[str]]], word: str, r: int, c: int, d: str) -> int:
    """Number of crossings if the word can go here legally, else -1."""
    dr, dc = (0, 1) if d == "across" else (1, 0)
    cells = _cells(word, r, c, d)
    before, after = (r - dr, c - dc), (cells[-1][0] + dr, cells[-1][1] + dc)
    if before in grid or after in grid:
        return -1  # would extend another word
    rows = [x for x, _ in grid] + [x for x, _ in cells]
    cols = [y for _, y in grid] + [y for _, y in cells]
    if max(rows) - min(rows) >= SIZE or max(cols) - min(cols) >= SIZE:
        return -1
    crossings = 0
    for (cr, cc), ch in zip(cells, word, strict=True):
        if (cr, cc) in grid:
            letter, dirs = grid[(cr, cc)]
            if letter != ch or d in dirs:
                return -1
            crossings += 1
        else:
            # A fresh letter may not touch anything sideways, or it would spell a stray word.
            side = [(cr + dc, cc + dr), (cr - dc, cc - dr)]
            if any(s in grid for s in side):
                return -1
    return crossings


def build_grid(entries: list[dict[str, str]], rng: Any, max_words: int = MAX_WORDS) -> list[dict[str, Any]]:
    """Place as many entries as fit (up to max_words), normalised so the top-left is (0, 0)."""
    pool = sorted(entries, key=lambda e: (-len(e["word"]), rng.random()))
    if not pool:
        return []
    grid: dict[Cell, tuple[str, set[str]]] = {}
    placed: list[dict[str, Any]] = []

    def put(e: dict[str, str], r: int, c: int, d: str) -> None:
        for (cr, cc), ch in zip(_cells(e["word"], r, c, d), e["word"], strict=True):
            letter, dirs = grid.get((cr, cc), (ch, set()))
            grid[(cr, cc)] = (letter, dirs | {d})
        placed.append({"word": e["word"], "clue": e["clue"], "row": r, "col": c, "dir": d})

    put(pool[0], 0, 0, "across")
    used = {pool[0]["word"]}
    for _ in range(3):  # a few passes: later words can open spots for earlier misses
        for e in pool[1:]:
            if len(placed) >= max_words or e["word"] in used:
                continue
            best: list[tuple[int, int, int, str]] = []
            for (gr, gc), (letter, _) in list(grid.items()):
                for i, ch in enumerate(e["word"]):
                    if ch != letter:
                        continue
                    for d in ("across", "down"):
                        r, c = (gr, gc - i) if d == "across" else (gr - i, gc)
                        n = _fits(grid, e["word"], r, c, d)
                        if n > 0:
                            best.append((n, r, c, d))
            if best:
                top = max(b[0] for b in best)
                _, r, c, d = rng.choice([b for b in best if b[0] == top])
                put(e, r, c, d)
                used.add(e["word"])
    r0 = min(r for r, _ in grid)
    c0 = min(c for _, c in grid)
    for p in placed:
        p["row"] -= r0
        p["col"] -= c0
    return placed


class CrosswordRace(Game):
    game_id: ClassVar[str] = "crossword"
    title: ClassVar[str] = "Crossword Race"
    blurb: ClassVar[str] = (
        "A brand-new crossword every game. Race your friends to fill it in: first right answer "
        "takes the points, wrong guesses cost you a beat."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"solve": 240.0}

    def start(self) -> None:
        placed: list[dict[str, Any]] = []
        for _ in range(5):  # a handful of tries for a roomy grid
            entries = [CROSSWORD_ENTRIES[i] for i in self.deal("entries", len(CROSSWORD_ENTRIES), 40)]
            attempt = build_grid(entries, self.rng)
            if len(attempt) > len(placed):
                placed = attempt
            if len(placed) >= MIN_WORDS + 2:
                break
        # Number the grid the usual way: top-to-bottom, left-to-right over word starts.
        starts = sorted({(p["row"], p["col"]) for p in placed})
        number = {rc: i + 1 for i, rc in enumerate(starts)}
        placed.sort(key=lambda p: (p["dir"] != "across", number[(p["row"], p["col"])]))
        self.clues: list[dict[str, Any]] = [
            {**p, "id": i, "num": number[(p["row"], p["col"])], "solved_by": None}
            for i, p in enumerate(placed)
        ]
        self.letters: dict[Cell, str] = {}
        for p in self.clues:
            for rc, ch in zip(_cells(p["word"], p["row"], p["col"], p["dir"]), p["word"], strict=True):
                self.letters[rc] = ch
        self.numbers = number
        self.revealed: set[Cell] = set()
        self.locked_until: dict[str, float] = {}
        self.started_at = self.clock()
        self.hint_level = 0
        self.phase = "solve"
        self.set_deadline(self.timings["solve"])
        self.bump()

    def _reveal_word(self, clue: dict[str, Any]) -> None:
        self.revealed.update(_cells(clue["word"], clue["row"], clue["col"], clue["dir"]))

    def _apply_hints(self) -> None:
        elapsed = self.clock() - self.started_at
        level = sum(1 for t in HINT_TIMES if elapsed >= t)
        while self.hint_level < level:
            self.hint_level += 1
            for clue in self.clues:
                if clue["solved_by"] is None:
                    cells = _cells(clue["word"], clue["row"], clue["col"], clue["dir"])
                    # Hint 1: the first letter. Hint 2: the middle one.
                    self.revealed.add(cells[0] if self.hint_level == 1 else cells[len(cells) // 2])
            self.bump()

    def _finish(self) -> None:
        self.revealed = set(self.letters)
        self.phase = "final"
        self.deadline = None
        self.finished = True
        self.bump()

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        if action.get("a") != "guess":
            raise GameError("bad_action", "Unknown action")
        if self.phase != "solve":
            raise GameError("wrong_phase", "The crossword is finished")
        idx = as_int(action.get("clue"), lo=0, hi=len(self.clues) - 1, field="Clue")
        raw = action.get("answer")
        if not isinstance(raw, str) or len(raw) > 20:
            raise GameError("bad_input", "Type a word")
        guess = re.sub(r"\s+", "", raw).upper()
        if not re.fullmatch(r"[A-Z]{1,15}", guess):
            raise GameError("bad_input", "Letters only")
        clue = self.clues[idx]
        if clue["solved_by"] is not None:
            raise GameError("already_solved", "Someone beat you to that one")
        now = self.clock()
        if now < self.locked_until.get(pid, 0.0):
            raise GameError("cooldown", "Steady! Try again in a moment")
        if guess != clue["word"]:
            self.locked_until[pid] = now + LOCKOUT
            raise GameError("wrong", "Not quite")
        clue["solved_by"] = pid
        self.add_points(pid, 40 + 10 * len(clue["word"]))
        self._reveal_word(clue)
        self.bump()
        if all(c["solved_by"] is not None for c in self.clues):
            self._finish()

    def tick(self) -> None:
        if self.finished:
            return
        self._apply_hints()
        if self.expired():
            self._finish()

    def advance(self) -> None:
        if not self.finished:
            self._finish()

    def view_for(self, pid: str) -> dict[str, Any]:
        rows = max((r for r, _ in self.letters), default=0) + 1
        cols = max((c for _, c in self.letters), default=0) + 1
        final = self.phase == "final"
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": 1,
            "rounds": 1,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "width": cols,
            "height": rows,
            # Only revealed letters: solved words, hints, or everything once the game is over.
            "cells": [
                {
                    "row": r,
                    "col": c,
                    "num": self.numbers.get((r, c)),
                    "letter": ch if (r, c) in self.revealed else None,
                }
                for (r, c), ch in sorted(self.letters.items())
            ],
            "clues": [
                {
                    "id": cl["id"],
                    "num": cl["num"],
                    "dir": cl["dir"],
                    "row": cl["row"],
                    "col": cl["col"],
                    "len": len(cl["word"]),
                    "clue": cl["clue"],
                    "solved_by": cl["solved_by"],
                    **({"answer": cl["word"]} if final or cl["solved_by"] is not None else {}),
                }
                for cl in self.clues
            ],
            "hint_level": self.hint_level,
            "locked_for": max(0.0, self.locked_until.get(pid, 0.0) - self.clock()),
        }
        return view

    def summary(self) -> dict[str, Any]:
        solved = sum(1 for c in self.clues if c["solved_by"] is not None)
        return {"players": len(self.players), "words": len(self.clues), "solved": solved}
