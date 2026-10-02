"""Game engine contract.

Every game is a small state machine that is *server-authoritative*:
clients only send intents, and `view_for(player_id)` is the single place that
decides what a given player may see. Secrets (the killer, the sealed price
modifier, other players' rankings) must never appear in another player's view.
"""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar


class GameError(Exception):
    """A player did something invalid. The message is safe to show to them."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Player:
    id: str
    name: str
    connected: bool = True
    score: int = 0


def as_int(value: Any, *, lo: int, hi: int, field: str) -> int:
    """Strictly coerce untrusted input to a bounded int (bools are rejected)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise GameError("bad_input", f"{field} must be a whole number")
    if value < lo or value > hi:
        raise GameError("bad_input", f"{field} is out of range")
    return value


class Game(ABC):
    game_id: ClassVar[str]
    title: ClassVar[str]
    blurb: ClassVar[str]
    min_players: ClassVar[int]
    max_players: ClassVar[int]

    def __init__(
        self,
        players: list[Player],
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
        timings: dict[str, float] | None = None,
    ) -> None:
        if not self.min_players <= len(players) <= self.max_players:
            raise GameError(
                "bad_player_count",
                f"{self.title} needs {self.min_players}-{self.max_players} players",
            )
        self.players = players
        self.rng: random.Random = rng or random.SystemRandom()
        self.clock = clock
        self.timings = {**self.default_timings(), **(timings or {})}
        self.version = 0
        self.phase = "init"
        self.round = 0
        self.deadline: float | None = None
        self.finished = False
        self.round_scores: dict[str, int] = {p.id: 0 for p in players}

    # --- helpers -----------------------------------------------------------
    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {}

    @property
    def player_ids(self) -> list[str]:
        return [p.id for p in self.players]

    def name_of(self, pid: str) -> str:
        for p in self.players:
            if p.id == pid:
                return p.name
        return "?"

    def require_player(self, pid: str) -> None:
        if pid not in self.round_scores:
            raise GameError("not_in_game", "You are not part of this game")

    @property
    def stage(self) -> str:
        """Identifies the current wait. Unlike `version` it doesn't change when someone acts."""
        return f"{self.phase}:{self.round}"

    def bump(self) -> None:
        self.version += 1

    def set_deadline(self, seconds: float | None) -> None:
        self.deadline = None if seconds is None else self.clock() + seconds

    def remaining(self) -> float | None:
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - self.clock())

    def expired(self) -> bool:
        return self.deadline is not None and self.clock() >= self.deadline

    def add_points(self, pid: str, points: int) -> None:
        self.round_scores[pid] = self.round_scores.get(pid, 0) + points

    def scores(self) -> dict[str, int]:
        return dict(self.round_scores)

    # --- contract ----------------------------------------------------------
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def handle(self, pid: str, action: dict[str, Any]) -> None: ...

    @abstractmethod
    def tick(self) -> None:
        """Advance timers. Must be cheap and idempotent."""

    @abstractmethod
    def advance(self) -> None:
        """Host asked to skip the current wait."""

    @abstractmethod
    def view_for(self, pid: str) -> dict[str, Any]: ...

    def summary(self) -> dict[str, Any]:
        """Anonymous, PII-free record stored when a game ends."""
        return {"players": len(self.players)}
