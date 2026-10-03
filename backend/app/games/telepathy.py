"""Telepathy Tax: think like some of your friends, but not all of them.

Each round shows a category and six options. Everyone secretly picks one. You score 100 for every
*other* player who picked the same thing. The tax: if more than half the room picked your answer,
it was too obvious and the tax collector takes the lot (0 points). Picks stay secret until the
reveal; the view only ever says who has locked in.

Streaks: score in back-to-back rounds for a growing bonus. One mid-game round is announced as a
Contrarian round: no tax, and only a pick nobody else made scores.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Any, ClassVar

from .base import Game, GameError, as_int
from .content import TELEPATHY_CATEGORIES

POINTS_PER_MATCH = 100
STREAK_BONUS = 50  # per extra round in a scoring streak...
STREAK_CAP = 3  # ...up to +150
CONTRARIAN_POINTS = 200


class TelepathyTax(Game):
    game_id: ClassVar[str] = "telepathy"
    title: ClassVar[str] = "Telepathy Tax"
    blurb: ClassVar[str] = (
        "Everyone secretly picks an answer. Score for every mind that matches yours - "
        "but if more than half the room picked it, the tax collector takes the lot."
    )
    min_players: ClassVar[int] = 3
    max_players: ClassVar[int] = 8
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Each round: a category and six answers. Secretly pick one.",
        "You score 100 for every other player who picked the same thing as you.",
        "The tax: if MORE than half the room picked it, it was too obvious and nobody scores it.",
        "Score in back-to-back rounds for a streak bonus. In the Contrarian round, only a pick "
        "nobody else made scores.",
    )
    READING: ClassVar[frozenset[str]] = frozenset(["reveal"])

    ROUNDS = 6

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"pick": 35.0, "reveal": 15.0}

    def start(self) -> None:
        self.categories = [
            TELEPATHY_CATEGORIES[i]
            for i in self.deal("categories", len(TELEPATHY_CATEGORIES), self.ROUNDS, kind="telepathy")
        ]
        self.round = 0
        self.results: list[dict[str, Any]] = []
        self.final: dict[str, Any] | None = None
        self.streaks: dict[str, int] = {p.id: 0 for p in self.players}
        self.contrarian_round = self.rng.randrange(1, self.ROUNDS - 1)  # never the first or last
        self._enter_pick()

    @property
    def is_contrarian(self) -> bool:
        return self.round == self.contrarian_round

    def _enter_pick(self) -> None:
        self.picks: dict[str, int] = {}
        self.phase = "pick"
        self.set_deadline(self.timings["pick"])
        self.bump()

    def _reveal(self) -> None:
        counts = Counter(self.picks.values())
        majority = len(self.players) / 2
        contrarian = self.is_contrarian
        taxed = [] if contrarian else sorted(opt for opt, c in counts.items() if c > majority)
        points: dict[str, int] = {}
        bonus: dict[str, int] = {}
        for p in self.players:
            opt = self.picks.get(p.id)
            if opt is None:
                base = 0
            elif contrarian:
                base = CONTRARIAN_POINTS if counts[opt] == 1 else 0
            else:
                base = 0 if opt in taxed else POINTS_PER_MATCH * (counts[opt] - 1)
            self.streaks[p.id] = self.streaks[p.id] + 1 if base > 0 else 0
            extra = STREAK_BONUS * min(self.streaks[p.id] - 1, STREAK_CAP) if self.streaks[p.id] >= 2 else 0
            if opt is not None:
                points[p.id] = base + extra
                bonus[p.id] = extra
            self.add_points(p.id, base + extra)
        self.results.append(
            {
                "category": self.categories[self.round],
                "picks": dict(self.picks),
                "points": points,
                "bonus": bonus,
                "taxed": taxed,
                "contrarian": contrarian,
                "streaks": dict(self.streaks),
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
    def peek(self, pid: str) -> str | None:
        """Power card: the most popular pick so far this round (not whose)."""
        others = [o for p, o in self.picks.items() if p != pid]
        if self.phase != "pick" or not others:
            return None
        top = max(set(others), key=others.count)
        name = self.categories[self.round]["options"][top]
        return f"{others.count(top)} of the picks so far are on {name}."

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
            "contrarian": self.is_contrarian and self.phase != "final",
            "streaks": dict(self.streaks),  # public: it only follows from revealed rounds
        }
        if self.phase == "reveal":
            view["result"] = self.results[-1]
        if self.phase == "final" and self.final is not None:
            view["final"] = self.final
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.final:
            return []
        out: list[dict[str, str]] = []
        meld = self.final["mind_meld"]
        if meld:
            a, b = (self.name_of(x) for x in meld["players"])
            out.append(
                {"icon": "🧠", "title": "Mind meld", "text": f"{a} and {b} matched {meld['matches']} times"}
            )
        best: dict[str, int] = {}
        for r in self.results:
            for pid, n in r["streaks"].items():
                best[pid] = max(best.get(pid, 0), n)
        if best:
            hot = max(best, key=lambda p: best[p])
            if best[hot] >= 3:
                text = f"{self.name_of(hot)} scored {best[hot]} rounds in a row"
                out.append({"icon": "🔥", "title": "On a streak", "text": text})
        for r in self.results:
            if r["contrarian"]:
                wolves = [self.name_of(p) for p, pts in r["points"].items() if pts - r["bonus"].get(p, 0) > 0]
                if wolves:
                    out.append(
                        {
                            "icon": "🐺",
                            "title": "Lone wolf",
                            "text": f"{', '.join(wolves)} went their own way",
                        }
                    )
        taxed: dict[str, int] = {}
        for r in self.results:
            for pid, opt in r["picks"].items():
                if opt in r["taxed"]:
                    taxed[pid] = taxed.get(pid, 0) + 1
        if taxed:
            magnet = max(taxed, key=lambda p: taxed[p])
            if taxed[magnet] >= 3:
                text = f"{self.name_of(magnet)} paid the tax {taxed[magnet]} times"
                out.append({"icon": "🧾", "title": "Tax magnet", "text": text})
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "rounds": len(self.results)}
