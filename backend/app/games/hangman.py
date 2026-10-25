"""Hangman: one player sets a word, the rest take turns guessing letters before the drawing is finished.

Each round a different player is the setter: they pick one of three suggested words or type their own
(letters and spaces, with an optional hint). The others take turns: guess a letter, or try to solve the
whole thing. A right letter is worth 50 for each time it appears and earns another go; a wrong letter
or a wrong solve adds a piece to the drawing and passes the turn. Six pieces and the word wins: the
setter scores 300. Solving it scores 200, plus 25 for every letter still hidden.

Secrecy: only the setter sees the word until the round ends (the TV and the audience see the blanks).
Every guesser has a turn clock; the host can skip the reveal but not a turn or the setting.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from .base import Game, GameError
from .content import DRAW_WORDS

MISSES = 6  # head, body, two arms, two legs
LETTER_POINTS = 50
SOLVE_POINTS = 200
SOLVE_BONUS = 25  # per letter still hidden
SETTER_POINTS = 300
SUGGESTIONS = 3
WORD = re.compile(r"[a-z]+( [a-z]+){0,3}")


def clean_word(raw: Any) -> str | None:
    """Letters and single spaces, 3-24 characters, at least 3 letters; lower case."""
    if not isinstance(raw, str):
        return None
    s = " ".join(raw.strip().lower().split())
    if not 3 <= len(s) <= 24 or not WORD.fullmatch(s) or sum(c.isalpha() for c in s) < 3:
        return None
    return s


class Hangman(Game):
    game_id: ClassVar[str] = "hangman"
    title: ClassVar[str] = "Hangman"
    blurb: ClassVar[str] = (
        "Take turns setting a word for the room. Guess letters, steal the solve, and beat the drawing "
        "before it's finished."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True
    OPTIONS: ClassVar[dict[str, list[str]]] = {"sets": ["1", "2"]}
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Each round one player sets a word (or picks one of three) for everyone else.",
        "Take turns: guess a letter, or solve it. A right letter is 50 a time and you go again.",
        "A wrong guess adds to the drawing. Six and the word wins: the setter scores 300.",
        "Solving scores 200, plus 25 for every letter still hidden.",
    )
    READING: ClassVar[frozenset[str]] = frozenset(["reveal"])

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"set": 40.0, "turn": 25.0, "reveal": 9.0}

    def start(self) -> None:
        self.order = list(self.player_ids)
        self.rng.shuffle(self.order)
        self.rounds = len(self.order) * int(self.options.get("sets", "1"))
        self.history: list[dict[str, Any]] = []
        self.round = 0
        self._set()

    @property
    def setter(self) -> str:
        return self.order[self.round % len(self.order)]

    @property
    def guessers(self) -> list[str]:
        i = self.order.index(self.setter)
        return self.order[i + 1 :] + self.order[:i]  # the player after the setter goes first

    def _set(self) -> None:
        picks = self.deal("words", len(DRAW_WORDS), SUGGESTIONS, deck="drawguess:words")
        self.suggestions = [DRAW_WORDS[i].replace("_", " ") for i in picks]
        self.word = ""
        self.hint = ""
        self.guessed: list[str] = []  # letters, in the order guessed
        self.misses: list[str] = []  # wrong letters and wrong solves
        self.turn = 0
        self.solver: str | None = None
        self.result: dict[str, Any] | None = None
        self.phase = "set"
        self.set_deadline(self.timings["set"])
        self.bump()

    def _begin(self, word: str, hint: str) -> None:
        self.word, self.hint = word, hint
        self.phase = "guess"
        self.set_deadline(self.timings["turn"])
        self.bump()

    @property
    def guesser(self) -> str:
        return self.guessers[self.turn % len(self.guessers)]

    def _hidden(self) -> int:
        return sum(1 for c in self.word if c.isalpha() and c not in self.guessed)

    # -- actions --------------------------------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind == "set":
            self._choose(pid, action)
        elif kind == "letter":
            self._letter(pid, action.get("letter"))
        elif kind == "solve":
            self._solve(pid, action.get("word"))
        else:
            raise GameError("bad_action", "Unknown action")

    def _choose(self, pid: str, action: dict[str, Any]) -> None:
        if self.phase != "set":
            raise GameError("wrong_phase", "The word is already set")
        if pid != self.setter:
            raise GameError("not_setter", "It's someone else's turn to set the word")
        word = clean_word(action.get("word"))
        if word is None:
            raise GameError("bad_input", "3-24 letters (spaces allowed), no numbers or symbols")
        hint = action.get("hint", "")
        if not isinstance(hint, str) or not hint.isprintable() or len(hint) > 40:
            raise GameError("bad_input", "Keep the hint under 40 characters")
        hint = " ".join(hint.split())
        if word.replace(" ", "") in hint.lower().replace(" ", ""):
            raise GameError("bad_input", "The hint can't give the word away")
        self._begin(word, hint)

    POWERS: ClassVar[dict[str, dict[str, str]]] = {
        "hangman_vowel": {
            "name": "Reveal a vowel",
            "icon": "🅰️",
            "text": "Show a hidden vowel on your turn (no points)",
        },
    }

    def use_power(self, pid: str, item: str) -> str | None:
        if item != "hangman_vowel":
            return super().use_power(pid, item)
        self._turn_check(pid)
        vowels = [v for v in "aeiou" if v in self.word and v not in self.guessed]
        # never the last hidden letters: the word is still for someone to solve
        vowels = [v for v in vowels if self._hidden() - self.word.count(v) >= 1]
        if not vowels:
            raise GameError("not_now", "No vowel left to reveal")
        v = self.rng.choice(vowels)
        self.guessed.append(v)
        self.bump()
        return f'The word has an "{v.upper()}".'

    def _turn_check(self, pid: str) -> None:
        if self.phase != "guess":
            raise GameError("wrong_phase", "No guessing right now")
        if pid != self.guesser:
            raise GameError("not_your_turn", "Not your turn")

    def _letter(self, pid: str, raw: Any) -> None:
        self._turn_check(pid)
        if not isinstance(raw, str) or len(raw) != 1 or not "a" <= raw.lower() <= "z":
            raise GameError("bad_input", "One letter, A to Z")
        letter = raw.lower()
        if letter in self.guessed or letter in self.misses:
            raise GameError("used", "That letter's been tried")
        hits = self.word.count(letter)
        if hits:
            self.guessed.append(letter)
            self.add_points(pid, LETTER_POINTS * hits)
            if self._hidden() == 0:
                self.solver = pid
                return self._reveal()
            self.set_deadline(self.timings["turn"])  # a right letter: go again
            self.bump()
        else:
            self._miss(letter)

    def _solve(self, pid: str, raw: Any) -> None:
        self._turn_check(pid)
        attempt = clean_word(raw)
        if attempt is None:
            raise GameError("bad_input", "Type the whole word (letters and spaces)")
        if attempt == self.word:
            self.add_points(pid, SOLVE_POINTS + SOLVE_BONUS * self._hidden())
            self.guessed.extend(sorted({c for c in self.word if c.isalpha()} - set(self.guessed)))
            self.solver = pid
            self._reveal()
        else:
            self._miss(f"“{attempt}”")

    def _miss(self, what: str) -> None:
        self.misses.append(what)
        if len(self.misses) >= MISSES:
            self.add_points(self.setter, SETTER_POINTS)
            return self._reveal()
        self.turn += 1
        self.set_deadline(self.timings["turn"])
        self.bump()

    def _reveal(self) -> None:
        self.result = {
            "word": self.word,
            "solver": self.solver,
            "setter": self.setter,
            "misses": len(self.misses),
        }
        self.history.append(dict(self.result))
        self.phase = "reveal"
        self.set_deadline(self.timings["reveal"])
        self.bump()

    # -- clocks ---------------------------------------------------------------------------------------
    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "set":  # out of time: the first suggestion
            self._begin(self.suggestions[0], "")
        elif self.phase == "guess":  # out of time: that's a miss, and the next player's go
            self._miss("⏱")
        elif self.phase == "reveal":
            if self.round + 1 >= self.rounds:
                self.phase = "final"
                self.deadline = None
                self.finished = True
                self.bump()
            else:
                self.round += 1
                self._set()

    def skip(self) -> bool:
        """The reveal only: a skip mid-round would cost the player on turn a guess."""
        if self.phase != "reveal":
            return False
        self.advance()
        return True

    def chat_blocked(self, pid: str, text: str) -> str | None:
        """The setter knows the word: they can't type it into the chat."""
        if (
            self.phase == "guess"
            and pid == self.setter
            and self.word.replace(" ", "") in re.sub(r"[^a-z]", "", text.lower())
        ):
            return "No giving the word away!"
        return None

    def peek(self, pid: str) -> str | None:
        """Power card: one hidden letter of the word (to a guesser)."""
        if self.phase != "guess" or pid == self.setter:
            return None
        hidden = sorted({c for c in self.word if c.isalpha() and c not in self.guessed})
        return f"There's a “{self.rng.choice(hidden).upper()}” in it." if hidden else None

    # -- views ----------------------------------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        out = self.phase in ("reveal", "final")
        knows = out or pid == self.setter
        pattern = [c if c == " " or c in self.guessed or out else None for c in self.word]
        return {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": self.rounds,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "setter": self.setter,
            "guesser": self.guesser if self.phase == "guess" else None,
            "order": self.guessers,
            "pattern": pattern if self.phase != "set" else [],
            "hint": self.hint,
            "guessed": list(self.guessed),
            "misses": list(self.misses),
            "max_misses": MISSES,
            "suggestions": list(self.suggestions) if pid == self.setter and self.phase == "set" else [],
            "word": self.word if knows and self.phase != "set" else None,
            "result": self.result if out else None,
            "scores": self.scores(),
            "history": self.history if self.phase == "final" else None,
        }

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        solves = [h for h in self.history if h["solver"]]
        if solves:
            best = min(solves, key=lambda h: h["misses"])
            out.append(
                {
                    "icon": "🕵️",
                    "title": "Code cracker",
                    "text": f"{self.name_of(best['solver'])} got “{best['word']}”",
                }
            )
        stumped = [h for h in self.history if not h["solver"]]
        if stumped:
            h = stumped[0]
            out.append(
                {
                    "icon": "🪢",
                    "title": "Stumped the room",
                    "text": f"Nobody got {self.name_of(h['setter'])}'s “{h['word']}”",
                }
            )
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "rounds": len(self.history)}
