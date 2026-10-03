"""Lowest Lonely Number: everyone secretly picks 1-20; the lowest number nobody else picked wins the pot.

Pure "they know that I know": 1 is the obvious pick, so nobody picks it, so someone should... Rounds
are quick. If nobody's number is lonely the pot rolls over to the next round, and the last round pays
double. Picks stay on the server until the reveal; a player who doesn't pick sits the round out.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError, as_int

ROUNDS = 8
TOP = 20
POT = 100
LAST_ROUND_MULTIPLIER = 2


def lonely_winner(picks: dict[str, int]) -> str | None:
    """Whoever holds the lowest number that exactly one person picked."""
    counts: dict[int, int] = {}
    for n in picks.values():
        counts[n] = counts.get(n, 0) + 1
    lonely = [n for n, c in counts.items() if c == 1]
    if not lonely:
        return None
    low = min(lonely)
    return next(p for p, n in picks.items() if n == low)


class LowestLonely(Game):
    game_id: ClassVar[str] = "lonely"
    title: ClassVar[str] = "Lowest Lonely Number"
    blurb: ClassVar[str] = (
        "Everyone secretly picks 1-20. The lowest number nobody else picked wins the pot. "
        "Nobody lonely? The pot rolls over."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"pick": 12.0, "reveal": 6.0}

    def start(self) -> None:
        self.history: list[dict[str, Any]] = []
        self.rollover = 0
        self.round = 0
        self._begin()

    def pot(self) -> int:
        base = POT * (LAST_ROUND_MULTIPLIER if self.round == ROUNDS - 1 else 1)
        return base + self.rollover

    def _begin(self) -> None:
        self.picks: dict[str, int] = {}
        self.result: dict[str, Any] | None = None
        self.phase = "pick"
        self.set_deadline(self.timings["pick"])
        self.bump()

    def _reveal(self) -> None:
        pot = self.pot()
        winner = lonely_winner(self.picks)
        if winner is not None:
            self.add_points(winner, pot)
            self.rollover = 0
        else:
            self.rollover = pot if self.round < ROUNDS - 1 else 0
        self.result = {"picks": dict(self.picks), "winner": winner, "pot": pot}
        self.history.append(self.result)
        self.phase = "reveal"
        self.set_deadline(self.timings["reveal"])
        self.bump()

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        if action.get("a") != "pick":
            raise GameError("bad_action", "Unknown action")
        if self.phase != "pick":
            raise GameError("wrong_phase", "Wait for the next round")
        if pid in self.picks:
            raise GameError("already_locked", "Your number is locked in")
        self.picks[pid] = as_int(action.get("n"), lo=1, hi=TOP, field="Number")
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
        elif self.round + 1 >= ROUNDS:
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
        else:
            self.round += 1
            self._begin()

    def peek(self, pid: str) -> str | None:
        """Power card: one number somebody has already picked this round (not whose)."""
        taken = sorted({n for p, n in self.picks.items() if p != pid})
        if self.phase != "pick" or not taken:
            return None
        return f"Someone has already picked {self.rng.choice(taken)}."

    def view_for(self, pid: str) -> dict[str, Any]:
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": ROUNDS,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "top": TOP,
            "pot": self.pot() if self.phase == "pick" else (self.result or {}).get("pot", 0),
            "rollover": self.rollover,
            "locked": sorted(self.picks),  # who has picked, never what
            "you": {"pick": self.picks.get(pid)},
            "wins": {p.id: sum(h["winner"] == p.id for h in self.history) for p in self.players},
        }
        if self.phase in ("reveal", "final") and self.result:
            view["result"] = self.result
        if self.phase == "final":
            view["history"] = self.history
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        ones = [h for h in self.history if h["winner"] and h["picks"][h["winner"]] == 1]
        if ones:
            out.append(
                {
                    "icon": "🐺",
                    "title": "Lone wolf",
                    "text": f"{self.name_of(ones[0]['winner'])} won with a 1",
                }
            )
        won = [h for h in self.history if h["winner"]]
        if won:
            big = max(won, key=lambda h: h["pot"])
            if big["pot"] > POT:
                out.append(
                    {
                        "icon": "💰",
                        "title": "Rollover raider",
                        "text": f"{self.name_of(big['winner'])} scooped a {big['pot']} pot "
                        f"with {big['picks'][big['winner']]}",
                    }
                )
        crowd: dict[int, int] = {}
        for h in self.history:
            for n in h["picks"].values():
                crowd[n] = crowd.get(n, 0) + 1
        if crowd:
            n, c = max(crowd.items(), key=lambda kv: (kv[1], -kv[0]))
            if c >= 4:
                out.append({"icon": "👥", "title": "Crowd favourite", "text": f"{n} got picked {c} times"})
        return out

    def summary(self) -> dict[str, Any]:
        wins = [h["picks"][h["winner"]] for h in self.history if h["winner"]]
        return {"players": len(self.players), "avg_winning_number": round(sum(wins) / max(len(wins), 1), 1)}
