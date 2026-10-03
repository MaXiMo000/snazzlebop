"""Split or Steal: trust, betrayal, and a public record of both.

Each round the room is paired up (people who haven't faced each other first; with an odd count one
player sits out for a small bye). Every pair has a public pot. Both pick SPLIT or STEAL in secret:
both split, each takes half; one steals, the stealer takes it all; both steal, nobody gets a thing.
Everyone's record of splits and steals is public, so grudges build round by round. Each player can
send one canned line per round ("I'm splitting, promise") to soften up their partner: no free text.

Secrecy: choices stay on the server until the round's reveal. A player who doesn't choose splits.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError, as_int

ROUNDS = 5
BYE_POINTS = 50
LINES = (
    "I'm splitting 🤝",
    "Trust me 😇",
    "Don't you dare 😠",
    "We're friends, right? 🥺",
    "I've got a good feeling 🍀",
    "…",
)


class SplitOrSteal(Game):
    game_id: ClassVar[str] = "split"
    title: ClassVar[str] = "Split or Steal"
    blurb: ClassVar[str] = (
        "Paired up every round with a pot on the table. Both split: share it. One steals: they take "
        "it all. Both steal: nobody does. Everyone's record is public."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"choose": 25.0, "reveal": 9.0}

    def start(self) -> None:
        self.met: set[frozenset[str]] = set()
        self.byes: dict[str, int] = {p.id: 0 for p in self.players}
        self.record: dict[str, list[str]] = {p.id: [] for p in self.players}  # public history of choices
        self.history: list[dict[str, Any]] = []
        self.round = 0
        self._begin()

    def _pairs(self) -> tuple[list[tuple[str, str]], str | None]:
        ids = list(self.player_ids)
        self.rng.shuffle(ids)
        bye = None
        if len(ids) % 2:
            fewest = min(self.byes[p] for p in ids)
            bye = next(p for p in ids if self.byes[p] == fewest)
            ids.remove(bye)
        best: list[tuple[str, str]] | None = None
        best_repeats = 10**9
        for _ in range(40):  # random matchings; keep the one with the fewest rematches
            self.rng.shuffle(ids)
            pairs = [(ids[i], ids[i + 1]) for i in range(0, len(ids), 2)]
            repeats = sum(frozenset(pair) in self.met for pair in pairs)
            if repeats < best_repeats:
                best, best_repeats = pairs, repeats
            if repeats == 0:
                break
        return best or [], bye

    def _begin(self) -> None:
        pairs, bye = self._pairs()
        self.pairs = pairs
        self.bye = bye
        base = 100 * (self.round + 1)
        self.pots = {frozenset(p): base + 10 * self.rng.randint(0, 10) for p in pairs}
        self.choices: dict[str, str] = {}
        self.said: dict[str, int] = {}
        self.result: dict[str, Any] | None = None
        self.phase = "choose"
        self.set_deadline(self.timings["choose"])
        self.bump()

    def partner(self, pid: str) -> str | None:
        for a, b in self.pairs:
            if pid in (a, b):
                return b if pid == a else a
        return None

    def _reveal(self) -> None:
        outcome: list[dict[str, Any]] = []
        for a, b in self.pairs:
            pot = self.pots[frozenset((a, b))]
            ca, cb = self.choices.get(a, "split"), self.choices.get(b, "split")
            if ca == cb == "split":
                gain = {a: pot // 2, b: pot // 2}
            elif ca == cb == "steal":
                gain = {a: 0, b: 0}
            else:
                gain = {a: pot if ca == "steal" else 0, b: pot if cb == "steal" else 0}
            for pid in (a, b):
                self.add_points(pid, gain[pid])
            self.record[a].append(ca)
            self.record[b].append(cb)
            self.met.add(frozenset((a, b)))
            outcome.append({"players": [a, b], "pot": pot, "choices": {a: ca, b: cb}, "gain": gain})
        if self.bye:
            self.byes[self.bye] += 1
            self.add_points(self.bye, BYE_POINTS)
        self.result = {"pairs": outcome, "bye": self.bye}
        self.history.append(self.result)
        self.phase = "reveal"
        self.set_deadline(self.timings["reveal"])
        self.bump()

    def _next(self) -> None:
        if self.round + 1 >= ROUNDS:
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
        else:
            self.round += 1
            self._begin()

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if self.phase != "choose":
            raise GameError("wrong_phase", "Wait for the next round")
        if self.partner(pid) is None:
            raise GameError("bye", "You're sitting this round out")
        if kind == "say":
            if pid in self.said:
                raise GameError("already_said", "One line per round")
            self.said[pid] = as_int(action.get("line"), lo=0, hi=len(LINES) - 1, field="Line")
            self.bump()
            return
        if kind != "choose":
            raise GameError("bad_action", "Unknown action")
        choice = action.get("choice")
        if choice not in ("split", "steal"):
            raise GameError("bad_input", "Split or steal?")
        if pid in self.choices:
            raise GameError("already_locked", "Your choice is locked in")
        self.choices[pid] = choice
        self.bump()
        if all(p in self.choices for pair in self.pairs for p in pair):
            self._reveal()

    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "choose":
            self._reveal()
        elif self.phase == "reveal":
            self._next()

    def view_for(self, pid: str) -> dict[str, Any]:
        mate = self.partner(pid) if pid in self.byes else None
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": ROUNDS,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "pairs": [{"players": [a, b], "pot": self.pots[frozenset((a, b))]} for a, b in self.pairs],
            "bye": self.bye,
            "locked": sorted(self.choices),  # who has chosen, never what
            "said": {p: LINES[i] for p, i in self.said.items()},  # canned lines are public
            "lines": list(LINES),
            # The public record only: choices are added once revealed.
            "record": {
                p: {"split": r.count("split"), "steal": r.count("steal")} for p, r in self.record.items()
            },
            "you": {"partner": mate, "choice": self.choices.get(pid) if self.phase == "choose" else None},
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
        splits = {p: r.count("split") for p, r in self.record.items() if r}
        steals = {
            p: sum(
                1
                for h in self.history
                for pr in h["pairs"]
                if pr["choices"].get(p) == "steal" and pr["gain"][p] > 0
            )
            for p in self.record
        }
        if splits:
            saint = max(splits, key=lambda p: splits[p])
            if splits[saint] == len(self.record[saint]) and splits[saint] >= 3:
                out.append(
                    {"icon": "😇", "title": "Saint", "text": f"{self.name_of(saint)} split every single time"}
                )
        if steals:
            shark = max(steals, key=lambda p: steals[p])
            if steals[shark] >= 2:
                out.append(
                    {
                        "icon": "🦈",
                        "title": "Ice cold",
                        "text": f"{self.name_of(shark)} stole {steals[shark]} pots",
                    }
                )
        doom = [pr for h in self.history for pr in h["pairs"] if set(pr["choices"].values()) == {"steal"}]
        if doom:
            a, b = (self.name_of(x) for x in doom[-1]["players"])
            out.append(
                {"icon": "💥", "title": "Mutual destruction", "text": f"{a} and {b} both stole, both lost"}
            )
        return out

    def summary(self) -> dict[str, Any]:
        choices = [c for r in self.record.values() for c in r]
        return {
            "players": len(self.players),
            "split_rate": round(choices.count("split") / max(len(choices), 1), 2),
        }
