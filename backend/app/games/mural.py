"""Mole in the Mural: a hidden-role game with no free text.

A mural of 16 tiles hides one secret "painting". Every player knows which tile it is, except the
Mole. Over two hint rounds everyone secretly picks one tile as a hint; hints are revealed together
at the end of each round. Innocents' hints must share a colour or a kind with the painting (the
server enforces it). The Mole doesn't know the painting, so has to bluff from what others pick.
Then the room votes. A caught Mole gets one guess at the painting to steal the win.

Secrecy: the painting never reaches the Mole or a TV screen before the end; nobody sees anyone
else's hint before the round reveal; only the Mole is told they're the Mole. The Mole's hints are
never validated: rejecting one would tell them where the painting is.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, ClassVar

from .base import Game, GameError, as_int
from .content import MURAL_TILES

TILES = 16
HINT_ROUNDS = 2


def _related(a: dict[str, str], b: dict[str, str]) -> bool:
    return a["color"] == b["color"] or a["kind"] == b["kind"]


class MoleInTheMural(Game):
    game_id: ClassVar[str] = "mural"
    title: ClassVar[str] = "Mole in the Mural"
    blurb: ClassVar[str] = (
        "Everyone knows which tile is the secret painting - except the Mole. "
        "Drop hints, spot the bluffer, vote. A caught Mole gets one guess to steal the win."
    )
    min_players: ClassVar[int] = 4
    max_players: ClassVar[int] = 8

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"briefing": 20.0, "hint": 40.0, "vote": 40.0, "mole_guess": 25.0}

    # -- setup --------------------------------------------------------------
    def start(self) -> None:
        rng = self.rng
        painting = MURAL_TILES[self.deal("paintings", len(MURAL_TILES), 1)[0]]
        others = [t for t in MURAL_TILES if t is not painting]
        related = [t for t in others if _related(t, painting)]
        unrelated = [t for t in others if not _related(t, painting)]
        # Enough related tiles that every innocent has real choices for both rounds,
        # enough unrelated ones that a bluffing Mole can slip up.
        n_related = min(len(related), rng.randint(5, 7))
        tiles = rng.sample(related, n_related) + rng.sample(unrelated, TILES - 1 - n_related) + [painting]
        rng.shuffle(tiles)
        self.mural: list[dict[str, str]] = tiles
        self.target = tiles.index(painting)
        self.mole = rng.choice(self.player_ids)
        self.hints: list[dict[str, int]] = []  # revealed rounds only
        self.current: dict[str, int] = {}
        self.votes: dict[str, str] = {}
        self.caught: str | None = None
        self.guess: int | None = None
        self.result: dict[str, Any] | None = None
        self.round = 0
        self._enter("briefing")

    def _enter(self, phase: str) -> None:
        self.phase = phase
        self.set_deadline(self.timings[phase])
        self.bump()

    def _close_hint_round(self) -> None:
        self.hints.append(dict(self.current))
        self.current = {}
        if len(self.hints) < HINT_ROUNDS:
            self.round += 1
            self._enter("hint")
        else:
            self._enter("vote")

    def _close_vote(self) -> None:
        tally = Counter(self.votes.values())
        top = max(tally.values(), default=0)
        leaders = [p for p, c in tally.items() if c == top and top > 0]
        if leaders == [self.mole]:
            self.caught = self.mole
            self._enter("mole_guess")
        else:
            self._finish()

    def _finish(self) -> None:
        stole = self.caught is not None and self.guess == self.target
        if self.caught is None:
            self.add_points(self.mole, 300)
        elif stole:
            self.add_points(self.mole, 200)
        else:
            for pid in self.player_ids:
                if pid != self.mole:
                    self.add_points(pid, 150 + (50 if self.votes.get(pid) == self.mole else 0))
        self.result = {
            "mole": self.mole,
            "target": self.target,
            "caught": self.caught is not None,
            "guess": self.guess,
            "stole": stole,
            "tally": dict(Counter(self.votes.values())),
            "votes": dict(self.votes),
        }
        self.phase = "final"
        self.deadline = None
        self.finished = True
        self.bump()

    # -- actions ------------------------------------------------------------
    def _tile(self, action: dict[str, Any]) -> int:
        return as_int(action.get("tile"), lo=0, hi=TILES - 1, field="Tile")

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if kind == "hint":
            if self.phase != "hint":
                raise GameError("wrong_phase", "Hints are closed")
            if pid in self.current:
                raise GameError("already_locked", "Your hint is already in")
            tile = self._tile(action)
            if any(h.get(pid) == tile for h in self.hints):
                raise GameError("bad_input", "Pick a tile you haven't used yet")
            if pid != self.mole:  # never validate the Mole: a refusal would point at the painting
                if tile == self.target:
                    raise GameError("bad_input", "That's the painting itself! Hint at it instead")
                if not _related(self.mural[tile], self.mural[self.target]):
                    raise GameError("bad_input", "Hints must share a colour or a kind with the painting")
            self.current[pid] = tile
            self.bump()
            if len(self.current) == len(self.players):
                self._close_hint_round()
        elif kind == "vote":
            if self.phase != "vote":
                raise GameError("wrong_phase", "Voting isn't open")
            target = action.get("target")
            if not isinstance(target, str) or target not in self.round_scores or target == pid:
                raise GameError("bad_input", "Vote for another player")
            self.votes[pid] = target
            self.bump()
            if len(self.votes) == len(self.players):
                self._close_vote()
        elif kind == "guess":
            if self.phase != "mole_guess" or pid != self.mole:
                raise GameError("wrong_phase", "Only a caught Mole guesses")
            self.guess = self._tile(action)
            self._finish()
        else:
            raise GameError("bad_action", "Unknown action")

    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "briefing":
            self._enter("hint")
        elif self.phase == "hint":
            self._close_hint_round()
        elif self.phase == "vote":
            self._close_vote()
        elif self.phase == "mole_guess":
            self._finish()

    # -- views --------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        is_player = pid in self.round_scores
        is_mole = pid == self.mole
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": HINT_ROUNDS,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "mural": [dict(t) for t in self.mural],
            "you": {
                "is_mole": is_mole,
                # Only innocent players see the painting. Never the Mole, never a TV.
                "target": self.target if is_player and not is_mole else None,
            },
            "hinted": sorted(self.current) if self.phase == "hint" else [],
            "your_hint": self.current.get(pid) if self.phase == "hint" else None,
            "hints": [dict(h) for h in self.hints],
            "votes_in": len(self.votes),
            "you_voted": self.votes.get(pid),
            "caught": self.caught,
        }
        if self.phase == "final" and self.result:
            view["result"] = self.result
        return view

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "caught": bool(self.result and self.result["caught"])}
