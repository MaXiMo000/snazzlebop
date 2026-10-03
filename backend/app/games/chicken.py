"""Chicken Run: a pot that grows every second and a bomb nobody can see.

Each round, after a short "get ready", the pot starts climbing: value(t) = 20 x 1.15^t points. Tap
CASH OUT to bank the value at the moment the server gets your tap. Somewhere between 4 and 24
seconds a hidden bomb goes off: anyone still in gets nothing. The round's biggest cash-out takes a
+50 bonus for nerve. Five rounds.

Secrecy: the bomb time lives only here until it goes off. The run phase deliberately has no public
deadline (a countdown would give the bomb away); clients animate the value from `started_ago`.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError

ROUNDS = 5
BASE, GROWTH = 20.0, 1.15
BOMB_MIN, BOMB_MAX = 4.0, 24.0
NERVE_BONUS = 50


def value_at(t: float) -> int:
    return int(BASE * GROWTH ** max(0.0, t))


class ChickenRun(Game):
    game_id: ClassVar[str] = "chicken"
    title: ClassVar[str] = "Chicken Run"
    blurb: ClassVar[str] = (
        "The pot grows every second. Cash out before the hidden bomb goes off, or lose the lot. "
        "Twenty seconds of screaming, five times over."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"ready": 3.0, "boom": 7.0}

    def start(self) -> None:
        self.history: list[dict[str, Any]] = []
        self.round = 0
        self._ready()

    def _ready(self) -> None:
        self.bomb = self.rng.uniform(BOMB_MIN, BOMB_MAX)  # seconds after the run starts: secret
        self.cashed: dict[str, dict[str, Any]] = {}  # pid -> {"t", "value"}
        self.run_start: float | None = None
        self.result: dict[str, Any] | None = None
        self.phase = "ready"
        self.set_deadline(self.timings["ready"])
        self.bump()

    def _run(self) -> None:
        self.phase = "run"
        self.run_start = self.clock()
        self.set_deadline(None)  # no countdown: it would reveal the bomb
        self.bump()

    def elapsed(self) -> float:
        return 0.0 if self.run_start is None else self.clock() - self.run_start

    def _end_round(self) -> None:
        best = max(self.cashed.values(), key=lambda c: c["value"], default=None)
        champs = [p for p, c in self.cashed.items() if best and c["value"] == best["value"]]
        for pid, c in self.cashed.items():
            self.add_points(pid, c["value"])
        bonus = champs[0] if len(champs) == 1 else None
        if bonus:
            self.add_points(bonus, NERVE_BONUS)
        boomed = [p for p in self.player_ids if p not in self.cashed]
        bomb = round(self.bomb, 2)
        self.result = {
            "bomb": bomb,
            "bomb_value": value_at(bomb),
            "cashed": {p: dict(c) for p, c in self.cashed.items()},
            "boomed": boomed,
            "nerve": bonus,
        }
        self.history.append(self.result)
        self.phase = "boom"
        self.set_deadline(self.timings["boom"])
        self.bump()

    def _next(self) -> None:
        if self.round + 1 >= ROUNDS:
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
        else:
            self.round += 1
            self._ready()

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        if action.get("a") != "cash":
            raise GameError("bad_action", "Unknown action")
        if self.phase == "run" and self.elapsed() >= self.bomb:
            self._end_round()  # the tap arrived after the bang
            raise GameError("too_late", "BOOM! Too late")
        if self.phase != "run":
            raise GameError("wrong_phase", "Wait for the run")
        if pid in self.cashed:
            raise GameError("already_locked", "You already cashed out")
        # Value the published (rounded) time, so anyone can check the number from the time shown.
        t = round(self.elapsed(), 2)
        self.cashed[pid] = {"t": t, "value": value_at(t)}
        self.bump()
        if len(self.cashed) == len(self.players):
            self._end_round()

    def tick(self) -> None:
        if self.finished:
            return
        if self.phase == "run":
            if self.elapsed() >= self.bomb:
                self._end_round()
        elif self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "ready":
            self._run()
        elif self.phase == "run":
            self._end_round()  # host skip: the bomb goes off now
        elif self.phase == "boom":
            self._next()

    def view_for(self, pid: str) -> dict[str, Any]:
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": ROUNDS,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "base": BASE,
            "growth": GROWTH,
            "started_ago": round(self.elapsed(), 3) if self.phase == "run" else None,
            "cashed": {p: dict(c) for p, c in self.cashed.items()},  # who's out, and for how much: public
        }
        if self.phase in ("boom", "final") and self.result:
            view["result"] = self.result  # the bomb time, only once it has gone off
        if self.phase == "final":
            view["history"] = self.history
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        best = max(
            ((p, c["value"], c["t"]) for h in self.history for p, c in h["cashed"].items()),
            key=lambda x: x[1],
            default=None,
        )
        if best:
            text = f"{self.name_of(best[0])} held on for {best[2]:.1f}s and banked {best[1]}"
            out.append({"icon": "🐔", "title": "Nerves of steel", "text": text})
        booms: dict[str, int] = {}
        for h in self.history:
            for p in h["boomed"]:
                booms[p] = booms.get(p, 0) + 1
        if booms:
            unlucky = max(booms, key=lambda p: booms[p])
            if booms[unlucky] >= 2:
                text = f"{self.name_of(unlucky)} got blown up {booms[unlucky]} times"
                out.append({"icon": "💥", "title": "Kaboom", "text": text})
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "rounds": len(self.history)}
