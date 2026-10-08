"""Word Race: everyone races to guess the same secret five-letter word in six tries (Wordle rules).

Each guess must be a real word. Every letter comes back green (right letter, right spot), yellow (in the
word, wrong spot) or grey (not in the word, or no more copies of it). Duplicates follow the original:
greens are matched first, then yellows from left to right, never more yellows than the word has spare.

Hard mode (an option): every revealed hint must be used. Greens stay put, yellows must appear again.

Scoring per round: solved in n guesses pays (7 - n) x 100, so a first-guess solve is 600 and a sixth
is 100. The first solver gets +100 and the second +50. The round ends when everyone has finished (solved
or out of guesses) or the clock runs out. 1, 3 or 5 rounds; a fresh word each round.

Secrecy: the answer never leaves the server until the round's reveal. Your letters are yours alone:
everyone else (TV and audience too) sees only your colours, like a shared emoji grid, until the reveal.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError
from .content import WORD_ANSWERS, WORD_GUESSES, WORD_STEMS

LENGTH = 5
TRIES = 6
FIRST_BONUS, SECOND_BONUS = 100, 50
ROUNDS = {"3": 3, "5": 5, "1": 1}

GREEN, YELLOW, GREY = "g", "y", "x"


def mark(guess: str, answer: str) -> str:
    """Wordle colours for a guess, one letter per tile: "gyxxg". Greens first, then yellows left to
    right, each only while the answer still has an unmatched copy of that letter."""
    out = [GREY] * LENGTH
    spare: dict[str, int] = {}
    for i, (g, a) in enumerate(zip(guess, answer, strict=True)):
        if g == a:
            out[i] = GREEN
        else:
            spare[a] = spare.get(a, 0) + 1
    for i, g in enumerate(guess):
        if out[i] != GREEN and spare.get(g, 0) > 0:
            out[i] = YELLOW
            spare[g] -= 1
    return "".join(out)


ANSWER_SET = frozenset(WORD_ANSWERS)


def is_word(word: str) -> bool:
    if word in WORD_GUESSES or word in ANSWER_SET:
        return True
    return word.endswith("S") and word[:-1] in WORD_STEMS


def hard_mode_problem(guess: str, history: list[tuple[str, str]]) -> str | None:
    """Why a guess breaks hard mode (or None): known greens must stay, known yellows must be reused."""
    for word, colours in history:
        for i, (letter, c) in enumerate(zip(word, colours, strict=True)):
            if c == GREEN and guess[i] != letter:
                return f"Letter {i + 1} must be {letter}"
        need: dict[str, int] = {}
        for letter, c in zip(word, colours, strict=True):
            if c in (GREEN, YELLOW):
                need[letter] = need.get(letter, 0) + 1
        for letter, n in need.items():
            if guess.count(letter) < n:
                return f"Your guess must contain {letter}"
    return None


class WordRace(Game):
    game_id: ClassVar[str] = "wordrace"
    title: ClassVar[str] = "Word Race"
    blurb: ClassVar[str] = (
        "Everyone hunts the same secret five-letter word in six tries. Green, yellow, grey. "
        "Fewer guesses and faster solves score more."
    )
    min_players: ClassVar[int] = 1
    max_players: ClassVar[int] = 8
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True
    OPTIONS: ClassVar[dict[str, list[str]]] = {"rounds": ["3", "5", "1"], "mode": ["normal", "hard"]}
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Everyone hunts the same secret five-letter word. You get six guesses, and each must be a real word.",
        "🟩 green: right letter, right spot. 🟨 yellow: in the word, wrong spot. ⬛ grey: not in the word.",
        "You see everyone's colours as they go, never their letters (until the reveal).",
        "Solve it in n guesses for (7 - n) x 100 points. First solver +100, second +50.",
        "Hard mode: every hint you've been given must be used in your next guesses.",
    )
    READING: ClassVar[frozenset[str]] = frozenset({"reveal"})

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"play": 180.0, "reveal": 12.0}

    def start(self) -> None:
        self.total_rounds = ROUNDS.get(self.options.get("rounds", "3"), 3)
        self.hard = self.options.get("mode") == "hard"
        self.history: list[dict[str, Any]] = []
        self.round = 0
        self._begin()

    # -- rounds ---------------------------------------------------------------------------------------
    def _begin(self) -> None:
        self.answer = WORD_ANSWERS[self.deal("answers", len(WORD_ANSWERS), 1)[0]]
        self.board: dict[str, list[tuple[str, str]]] = {p: [] for p in self.player_ids}
        self.solved: list[str] = []  # in the order they solved
        self.gained: dict[str, int] = dict.fromkeys(self.player_ids, 0)
        self.phase = "play"
        self.set_deadline(self.timings["play"])
        self.bump()

    def _done(self, pid: str) -> bool:
        return pid in self.solved or len(self.board[pid]) >= TRIES

    def _reveal(self) -> None:
        self.history.append(
            {
                "answer": self.answer,
                "solved": list(self.solved),
                "tries": {p: len(rows) for p, rows in self.board.items()},
                "points": dict(self.gained),
            }
        )
        self.phase = "reveal"
        self.set_deadline(self.timings["reveal"])
        self.bump()

    # -- actions --------------------------------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        if action.get("a") != "guess":
            raise GameError("bad_action", "Unknown action")
        if self.phase != "play":
            raise GameError("wrong_phase", "Wait for the next word")
        if self._done(pid):
            raise GameError("finished", "You've finished this word")
        raw = action.get("word")
        if not isinstance(raw, str) or len(raw) != LENGTH:
            raise GameError("bad_input", "Five letters, please")
        word = raw.upper()
        if not word.isascii() or not word.isalpha():
            raise GameError("bad_input", "Letters only")
        if not is_word(word):
            raise GameError("not_a_word", "Not in the word list")
        rows = self.board[pid]
        if self.hard and (problem := hard_mode_problem(word, rows)):
            raise GameError("hard_mode", problem)
        colours = mark(word, self.answer)
        rows.append((word, colours))
        if colours == GREEN * LENGTH:
            self.solved.append(pid)
            bonus = FIRST_BONUS if len(self.solved) == 1 else SECOND_BONUS if len(self.solved) == 2 else 0
            points = (TRIES + 1 - len(rows)) * 100 + bonus
            self.gained[pid] = points
            self.add_points(pid, points)
        self.bump()
        if all(self._done(p) for p in self.player_ids):
            self._reveal()

    # -- clocks ---------------------------------------------------------------------------------------
    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "play":
            self._reveal()
        elif self.phase == "reveal":
            if self.round + 1 >= self.total_rounds:
                self.phase = "final"
                self.deadline = None
                self.finished = True
                self.bump()
            else:
                self.round += 1
                self._begin()

    # -- views ----------------------------------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        open_book = self.phase in ("reveal", "final")
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": self.total_rounds,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "hard": self.hard,
            "tries": TRIES,
            # Everyone's colours; letters only for your own rows (and for all once the word is out).
            "boards": {
                p: [{"word": w if open_book or p == pid else None, "marks": m} for w, m in rows]
                for p, rows in self.board.items()
            },
            "solved": list(self.solved),
            "gained": dict(self.gained) if open_book else {p: v for p, v in self.gained.items() if p == pid},
            "you": {
                "playing": pid in self.board,
                "done": pid in self.board and self._done(pid),
                "solved": pid in self.solved,
            },
            "answer": self.answer if open_book else None,
            "wins": {p: sum(1 for h in self.history if p in h["solved"]) for p in self.player_ids},
        }
        if self.phase == "final":
            view["history"] = self.history
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        quick = [(h["tries"][p], p, h["answer"]) for h in self.history for p in h["solved"]]
        if quick:
            n, p, word = min(quick)
            if n <= 3:
                out.append(
                    {"icon": "🎯", "title": "Mind reader", "text": f"{self.name_of(p)} found {word} in {n}"}
                )
        clutch = [(p, h["answer"]) for h in self.history for p in h["solved"] if h["tries"][p] == TRIES]
        if clutch:
            p, word = clutch[0]
            out.append(
                {"icon": "😅", "title": "Clutch", "text": f"{self.name_of(p)} got {word} on the last try"}
            )
        firsts: dict[str, int] = {}
        for h in self.history:
            if h["solved"]:
                firsts[h["solved"][0]] = firsts.get(h["solved"][0], 0) + 1
        if firsts:
            p = max(firsts, key=lambda q: firsts[q])
            out.append(
                {
                    "icon": "⚡",
                    "title": "Fastest fingers",
                    "text": f"{self.name_of(p)} solved first {firsts[p]}x",
                }
            )
        stumped = [h["answer"] for h in self.history if not h["solved"]]
        if stumped:
            out.append({"icon": "🤯", "title": "Stumper", "text": f"Nobody got {stumped[0]}"})
        return out

    def summary(self) -> dict[str, Any]:
        solves = [h["tries"][p] for h in self.history for p in h["solved"]]
        return {
            "players": len(self.players),
            "hard": self.hard,
            "rounds": len(self.history),
            "avg_tries": round(sum(solves) / max(len(solves), 1), 2),
        }
