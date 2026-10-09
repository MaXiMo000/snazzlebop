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

from .content import THEMED


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


class Deck:
    """Deals indices into a content pool without repeats until every card has been seen.

    Rooms keep their decks across games, so a party never sees the same prompt or item twice
    until the pool runs out. A reshuffle never opens with cards dealt just before it.
    """

    def __init__(self, size: int, rng: random.Random) -> None:
        if size < 1:
            raise ValueError("empty pool")
        self.size = size
        self.rng = rng
        self._stack: list[int] = []
        self._recent: list[int] = []

    def grow(self, size: int) -> None:
        """The pool gained items (e.g. freshly generated content): deal those first, keep memory."""
        if size <= self.size:
            return
        fresh = list(range(self.size, size))
        self.rng.shuffle(fresh)
        self._stack.extend(fresh)  # pop() takes from the end: new cards come out next
        self.size = size

    def _refill(self, n: int, out: list[int]) -> None:
        avoid = set(out) | set(self._recent[-min(n, self.size // 2) :])
        fresh = [i for i in range(self.size) if i not in avoid]
        self.rng.shuffle(fresh)
        held = [i for i in self._recent if i in avoid and i not in out]
        # pop() takes from the end: recent cards go to the bottom of the new pass.
        self._stack = held + fresh

    def draw(self, n: int, prefer: frozenset[int] | set[int] = frozenset()) -> list[int]:
        """n distinct cards. `prefer` (e.g. a theme's items) comes first while this pass still holds
        any of them; the rest of the pass is untouched, so nothing repeats either way."""
        if n > self.size:
            raise ValueError("pool smaller than the draw")
        out: list[int] = []
        if prefer:
            if not self._stack:
                self._refill(n, out)
            picks = [c for c in reversed(self._stack) if c in prefer][:n]
            if picks:
                chosen = set(picks)
                self._stack = [c for c in self._stack if c not in chosen]
                out.extend(picks)
        while len(out) < n:
            if not self._stack:
                self._refill(n, out)
            card = self._stack.pop()
            if card not in out:
                out.append(card)
        self._recent = (self._recent + out)[-self.size :]
        return out


class Game(ABC):
    game_id: ClassVar[str]
    title: ClassVar[str]
    blurb: ClassVar[str]
    min_players: ClassVar[int]
    max_players: ClassVar[int]
    # Host-chosen settings: option name -> allowed values (first = default). Validated by the hub.
    OPTIONS: ClassVar[dict[str, list[str]]] = {}
    # Plain-language rules, shown before the game starts and behind "How to play" during it.
    HOW_TO: ClassVar[tuple[str, ...]] = ()
    # Results/briefing phases the room can skip together: once every player taps Ready, it moves on.
    READING: ClassVar[frozenset[str]] = frozenset()
    # False for team games that are played on their own rather than in a show-night playlist.
    SHOW: ClassVar[bool] = True
    # True for the classics (board, card and party games everyone knows): their own lobby section.
    CLASSIC: ClassVar[bool] = False
    # True when the host may switch on Teams: two teams, the team's combined score wins. A game with an
    # official partner rule plays it (self.teams); the rest play as usual and the hub adds up the teams.
    TEAMS: ClassVar[bool] = False

    def __init__(
        self,
        players: list[Player],
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
        timings: dict[str, float] | None = None,
        decks: dict[str, Deck] | None = None,
        theme: str = "",
        options: dict[str, str] | None = None,
        teams: dict[str, int] | None = None,
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
        self.decks = decks if decks is not None else {}
        self.theme = theme  # a show pack (content.THEMES); "" = everything
        self.options = dict(options or {})
        ids = {p.id for p in players}
        self.teams: dict[str, int] = {p: t for p, t in (teams or {}).items() if p in ids}  # player -> 0/1
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

    def deal(self, pool: str, size: int, n: int, *, kind: str = "", deck: str = "") -> list[int]:
        """n distinct indices into a content pool, never repeating within this room's decks.

        `kind` names the content kind so a themed room gets that theme's items first; `deck` shares a
        deck with another game that deals from the same pool (e.g. the jackpot uses Price items)."""
        key = deck or f"{self.game_id}:{pool}"
        d = self.decks.get(key)
        if d is None or d.size > size:
            d = self.decks[key] = Deck(size, self.rng)
        d.grow(size)  # pools only grow at runtime; keep what this room has already seen
        prefer = THEMED.get(kind, {}).get(self.theme, set()) if kind and self.theme else set()
        return d.draw(n, prefer)

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

    # -- chat: who may talk to whom ------------------------------------------------------------------
    def chat_team(self, pid: str) -> tuple[str, str] | None:
        """This player's private team channel as (key, label), or None for no team chat. By default the
        Teams switch's two teams; games with their own teams override it (and partner games where talking
        privately would be cheating return None)."""
        team = self.teams.get(pid)
        return None if team is None else (f"team:{team}", ("Team Tangerine", "Team Teal")[team])

    def chat_muted(self, pid: str) -> bool:
        """True while the rules say this player must stay silent (a Codewords Spymaster mid-game)."""
        return False

    def peek(self, pid: str) -> str | None:
        """The Peek power card: one private line about a secret in the game as it stands right now (or None
        when there's nothing to see). Called only for a seated player; the line goes only to them."""
        return None

    def highlights(self) -> list[dict[str, str]]:
        """Moments worth a line in the show's highlight reel, once the game is over:
        [{"icon": "🎯", "title": "Sharpshooter", "text": "Bo guessed within $3"}]. Names are fine here
        (they only go to this room's screens)."""
        return []

    def summary(self) -> dict[str, Any]:
        """Anonymous, PII-free record stored when a game ends."""
        return {"players": len(self.players)}
