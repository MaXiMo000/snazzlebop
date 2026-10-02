"""Telepathy Tax: think like some of your friends, but not all of them.

Each round shows a category and six options. Everyone secretly picks one. You score 100 for every
*other* player who picked the same thing. The tax: if more than half the room picked your answer,
it was too obvious and the tax collector takes the lot (0 points). Picks stay secret until the
reveal; the view only ever says who has locked in.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Any, ClassVar

from .base import Game, GameError, as_int
from .content import TELEPATHY_CATEGORIES

POINTS_PER_MATCH = 100


class TelepathyTax(Game):
    game_id: ClassVar[str] = "telepathy"
    title: ClassVar[str] = "Telepathy Tax"
    blurb: ClassVar[str] = (
        "Everyone secretly picks an answer. Score for every mind that matches yours - "
        "but if more than half the room picked it, the tax collector takes the lot."
    )
    min_players: ClassVar[int] = 3
    max_players: ClassVar[int] = 8

    ROUNDS = 6

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"pick": 30.0, "reveal": 12.0}

    def start(self) -> None:
        self.categories = [
            TELEPATHY_CATEGORIES[i] for i in self.deal("categories", len(TELEPATHY_CATEGORIES), self.ROUNDS)
        ]
        self.round = 0
        self.results: list[dict[str, Any]] = []
        self.final: dict[str, Any] | None = None
        self._enter_pick()

    def _enter_pick(self) -> None:
        self.picks: dict[str, int] = {}
        self.phase = "pick"
        self.set_deadline(self.timings["pick"])
        self.bump()

    def _reveal(self) -> None:
        counts = Counter(self.picks.values())
        majority = len(self.players) / 2
        taxed = sorted(opt for opt, c in counts.items() if c > majority)
        points: dict[str, int] = {}
        for pid, opt in self.picks.items():
            points[pid] = 0 if opt in taxed else POINTS_PER_MATCH * (counts[opt] - 1)
            self.add_points(pid, points[pid])
        self.results.append(
            {
                "category": self.categories[self.round],
                "picks": dict(self.picks),
                "points": points,
                "taxed": taxed,
            }
        )
        self.phase = "reveal"
        self.set_deadline(self.timings["reveal"])
        self.bump()

    def _next(self) -> None:
        if self.round + 1 >= self.ROUNDS:
            self.final = {"history": self.results, "mind_meld": self._mind_meld()}
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
        else:
            self.round += 1
            self._enter_pick()

    def _mind_meld(self) -> dict[str, Any] | None:
        """The pair whose minds matched most often (at least twice)."""
        best: tuple[int, tuple[str, str]] | None = None
        for a, b in combinations(self.player_ids, 2):
            n = sum(1 for r in self.results if a in r["picks"] and r["picks"][a] == r["picks"].get(b))
            if n >= 2 and (best is None or n > best[0]):
                best = (n, (a, b))
        return {"players": list(best[1]), "matches": best[0]} if best else None

    # -- actions ------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        if action.get("a") != "pick":
            raise GameError("bad_action", "Unknown action")
        if self.phase != "pick":
            raise GameError("wrong_phase", "Picking is closed")
        if pid in self.picks:
            raise GameError("already_locked", "Your pick is already locked in")
        option = as_int(
            action.get("option"), lo=0, hi=len(self.categories[self.round]["options"]) - 1, field="Option"
        )
        self.picks[pid] = option
        self.bump()
        if len(self.picks) == len(self.players):
            self._reveal()

    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "pick":
            self._reveal()
        elif self.phase == "reveal":
            self._next()

    # -- views --------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        cat = self.categories[min(self.round, self.ROUNDS - 1)]
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": self.ROUNDS,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "category": {"title": cat["title"], "options": list(cat["options"])},
            "locked": sorted(self.picks) if self.phase == "pick" else [],
            "you_locked": pid in self.picks,
            # Only your own pick, and only while picking. Everyone's picks arrive with the reveal.
            "your_pick": self.picks.get(pid) if self.phase == "pick" else None,
        }
        if self.phase == "reveal":
            view["result"] = self.results[-1]
        if self.phase == "final" and self.final is not None:
            view["final"] = self.final
        return view

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "rounds": len(self.results)}
