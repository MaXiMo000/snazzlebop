"""On Your Head (the forehead guessing game): describe the word, your friend guesses it.

Players take turns as the guesser. During a 60-second turn everyone else sees a word and shouts clues
(no saying the word itself); anyone can tap Got it or Pass, and a new word comes up. The guesser can hold
their phone to their forehead instead ("forehead mode"): their phone then shows the word to the room
and they tilt it down for Got it, up for Pass. Every word got is 100 to the guesser and 25 to each
clue-giver. Everyone guesses once (or twice).

Secrecy: the guesser never gets the word in their view unless they switch forehead mode on (their
phone is facing the room then). The TV never shows it either: the guesser can see the TV.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError, as_int
from .content import DRAW_WORDS

GUESS_POINTS = 100
CLUE_POINTS = 25
DECK = 40  # words dealt per turn (nobody gets through 40 in a minute)


class OnYourHead(Game):
    game_id: ClassVar[str] = "onhead"
    title: ClassVar[str] = "On Your Head"
    blurb: ClassVar[str] = (
        "Phone on your forehead: everyone else sees the word and shouts clues. Guess as many as you can "
        "in a minute."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True
    OPTIONS: ClassVar[dict[str, list[str]]] = {"goes": ["1", "2"], "seconds": ["60", "45", "90"]}
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Take turns as the guesser. Everyone else sees the word: give clues, but never say it!",
        "Anyone can tap Got it or Pass. Or hold your phone to your head: tilt down for Got it, up to pass.",
        "Every word got: 100 to the guesser, 25 to each clue-giver.",
    )
    READING: ClassVar[frozenset[str]] = frozenset(["ready", "result"])

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"ready": 10.0, "result": 10.0}

    def start(self) -> None:
        self.order = list(self.player_ids)
        self.rng.shuffle(self.order)
        self.rounds = len(self.order) * int(self.options.get("goes", "1"))
        self.seconds = float(self.options.get("seconds", "60"))
        self.history: list[dict[str, Any]] = []
        self.round = 0
        self._ready()

    @property
    def guesser(self) -> str:
        return self.order[self.round % len(self.order)]

    def _ready(self) -> None:
        picks = self.deal("words", len(DRAW_WORDS), DECK, deck="drawguess:words")
        self.words = [DRAW_WORDS[i].replace("_", " ") for i in picks]
        self.n = 0  # the word up now
        self.got: list[str] = []
        self.passed: list[str] = []
        self.forehead = False
        self.phase = "ready"
        self.set_deadline(self.timings["ready"])
        self.bump()

    def _go(self) -> None:
        self.phase = "play"
        self.set_deadline(self.seconds)
        self.bump()

    # -- actions --------------------------------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind == "forehead":
            if pid != self.guesser:
                raise GameError("not_guesser", "Only the guesser holds it to their head")
            flag = action.get("on")
            if not isinstance(flag, bool):
                raise GameError("bad_input", "On or off?")
            self.forehead = flag
            self.bump()
            return
        if kind not in ("got", "pass"):
            raise GameError("bad_action", "Unknown action")
        if self.phase != "play":
            return  # a tap that lands just after the turn ended: nothing to mark
        if pid == self.guesser and not self.forehead:
            raise GameError("not_yours", "Your friends mark your answers (or use forehead mode)")
        n = as_int(action.get("n"), lo=0, hi=DECK - 1, field="Word")
        if n != self.n:
            return  # someone else already marked that word: nothing to do
        word = self.words[self.n]
        if kind == "got":
            self.got.append(word)
            self.add_points(self.guesser, GUESS_POINTS)
            for p in self.player_ids:
                if p != self.guesser:
                    self.add_points(p, CLUE_POINTS)
        else:
            self.passed.append(word)
        self.n += 1
        if self.n >= len(self.words):
            self._end()
        else:
            self.bump()

    def _end(self) -> None:
        self.history.append({"guesser": self.guesser, "got": list(self.got), "passed": list(self.passed)})
        self.phase = "result"
        self.set_deadline(self.timings["result"])
        self.bump()

    # -- clocks ---------------------------------------------------------------------------------------
    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "ready":
            self._go()
        elif self.phase == "play":
            self._end()
        elif self.phase == "result":
            if self.round + 1 >= self.rounds:
                self.phase = "final"
                self.deadline = None
                self.finished = True
                self.bump()
            else:
                self.round += 1
                self._ready()

    def skip(self) -> bool:
        """The get-ready and result screens; never a turn in progress (that would cut it short)."""
        if self.phase == "play":
            return False
        self.advance()
        return True

    def chat_muted(self, pid: str) -> bool:
        return self.phase == "play"  # clues are spoken, not typed (a typed word would give it away)

    # -- views ----------------------------------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        playing = self.phase == "play"
        sees = playing and pid != self.guesser and not pid.startswith("tv:")
        sees = sees or (playing and pid == self.guesser and self.forehead)
        return {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": self.rounds,
            "remaining": self.remaining(),
            "seconds": self.seconds,
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "guesser": self.guesser,
            "word": self.words[self.n] if sees else None,
            "n": self.n,
            "forehead": self.forehead,
            "got": list(self.got) if not playing or pid != self.guesser else [],
            "passed": list(self.passed) if not playing or pid != self.guesser else [],
            "count": len(self.got),
            "scores": self.scores(),
            "history": self.history if self.phase == "final" else None,
        }

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished or not self.history:
            return []
        best = max(self.history, key=lambda h: len(h["got"]))
        if not best["got"]:
            return []
        return [
            {
                "icon": "🧠",
                "title": "Mind meld",
                "text": f"{self.name_of(best['guesser'])} got {len(best['got'])} in one turn",
            }
        ]

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "rounds": len(self.history)}
