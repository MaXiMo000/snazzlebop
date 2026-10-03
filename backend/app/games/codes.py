"""Code Crackers: set a secret code, then race to crack everyone else's.

Everyone sets a 4-symbol code from 6 symbols (repeats allowed; a random one if the setup timer runs
out). Then it's a free-for-all: guess anyone's code and get Mastermind feedback, "hits" (right symbol,
right place) and "near" (right symbol, wrong place). First to crack a code scores 300, second 200,
later 100. A code nobody cracks earns its owner 200. A short cooldown between guesses keeps it a
brain race, not a button-mashing one.

Secrecy: codes, guesses and feedback are private to the guesser until the end; the public board only
says who has cracked whom.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, ClassVar

from .base import Game, GameError, as_int

LENGTH = 4
SYMBOLS = 6
CRACK_POINTS = (300, 200)  # first, second; later crackers get LATE_POINTS
LATE_POINTS = 100
UNCRACKED_POINTS = 200
COOLDOWN = 1.5  # seconds between one player's guesses


def feedback(code: list[int], guess: list[int]) -> tuple[int, int]:
    """(hits, near): hits = right symbol in the right place; near = right symbol in the wrong place."""
    hits = sum(c == g for c, g in zip(code, guess, strict=True))
    common = sum((Counter(code) & Counter(guess)).values())
    return hits, common - hits


class CodeCrackers(Game):
    game_id: ClassVar[str] = "codes"
    title: ClassVar[str] = "Code Crackers"
    blurb: ClassVar[str] = (
        "Everyone hides a secret 4-symbol code, then races to crack everyone else's with "
        "Mastermind clues. First to crack a code scores big."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"set": 30.0, "crack": 240.0}

    def start(self) -> None:
        self.codes: dict[str, list[int]] = {}
        self.guesses: dict[str, dict[str, list[dict[str, Any]]]] = {p.id: {} for p in self.players}
        self.cracked: dict[str, list[str]] = {p.id: [] for p in self.players}  # owner -> crackers in order
        self.next_guess: dict[str, float] = {}
        self.round = 0
        self.phase = "set"
        self.set_deadline(self.timings["set"])
        self.bump()

    def _code(self, raw: Any) -> list[int]:
        if not isinstance(raw, list) or len(raw) != LENGTH:
            raise GameError("bad_input", f"A code is {LENGTH} symbols")
        return [as_int(x, lo=0, hi=SYMBOLS - 1, field="Symbol") for x in raw]

    def _begin_crack(self) -> None:
        for p in self.players:
            if p.id not in self.codes:
                self.codes[p.id] = [self.rng.randrange(SYMBOLS) for _ in range(LENGTH)]
        self.phase = "crack"
        self.set_deadline(self.timings["crack"])
        self.bump()

    def _finish(self) -> None:
        for owner, crackers in self.cracked.items():
            if not crackers:
                self.add_points(owner, UNCRACKED_POINTS)
        self.phase = "final"
        self.deadline = None
        self.finished = True
        self.bump()

    def _all_cracked(self) -> bool:
        n = len(self.players)
        return all(len(c) == n - 1 for c in self.cracked.values())

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind == "set":
            if self.phase != "set":
                raise GameError("wrong_phase", "Codes are set")
            if pid in self.codes:
                raise GameError("already_locked", "Your code is set")
            self.codes[pid] = self._code(action.get("code"))
            self.bump()
            if len(self.codes) == len(self.players):
                self._begin_crack()
            return
        if kind != "guess":
            raise GameError("bad_action", "Unknown action")
        if self.phase != "crack":
            raise GameError("wrong_phase", "Not cracking yet")
        target = action.get("target")
        if not isinstance(target, str) or target not in self.codes or target == pid:
            raise GameError("bad_input", "Pick someone else's code")
        if pid in self.cracked[target]:
            raise GameError("already_cracked", "You already cracked that one")
        now = self.clock()
        if now < self.next_guess.get(pid, 0.0):
            raise GameError("cooldown", "Steady! One guess at a time")
        guess = self._code(action.get("code"))
        hits, near = feedback(self.codes[target], guess)
        self.next_guess[pid] = now + COOLDOWN
        self.guesses[pid].setdefault(target, []).append({"code": guess, "hits": hits, "near": near})
        if hits == LENGTH:
            order = len(self.cracked[target])
            self.add_points(pid, CRACK_POINTS[order] if order < len(CRACK_POINTS) else LATE_POINTS)
            self.cracked[target].append(pid)
        self.bump()
        if self._all_cracked():
            self._finish()

    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "set":
            self._begin_crack()
        elif self.phase == "crack":
            self._finish()

    def view_for(self, pid: str) -> dict[str, Any]:
        final = self.phase == "final"
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": 1,
            "rounds": 1,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "length": LENGTH,
            "symbols": SYMBOLS,
            "set": sorted(self.codes) if self.phase == "set" else [],
            "cracked": {k: list(v) for k, v in self.cracked.items()},  # who cracked whom: public
            "guess_counts": {p: sum(len(g) for g in gs.values()) for p, gs in self.guesses.items()},
            "you": {
                "code": list(self.codes.get(pid, [])),
                "guesses": {t: [dict(g) for g in gs] for t, gs in self.guesses.get(pid, {}).items()},
                "cooldown": max(0.0, self.next_guess.get(pid, 0.0) - self.clock()),
            },
        }
        if final:
            view["codes"] = {k: list(v) for k, v in self.codes.items()}
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        firsts: dict[str, int] = {}
        for crackers in self.cracked.values():
            if crackers:
                firsts[crackers[0]] = firsts.get(crackers[0], 0) + 1
        if firsts:
            ace = max(firsts, key=lambda p: firsts[p])
            out.append(
                {
                    "icon": "🔓",
                    "title": "Master cracker",
                    "text": f"{self.name_of(ace)} cracked {firsts[ace]} codes first",
                }
            )
        vault = [o for o, c in self.cracked.items() if not c]
        if vault:
            out.append(
                {
                    "icon": "🔐",
                    "title": "Unbreakable",
                    "text": f"Nobody cracked {self.name_of(vault[0])}'s code",
                }
            )
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "cracks": sum(len(c) for c in self.cracked.values())}
