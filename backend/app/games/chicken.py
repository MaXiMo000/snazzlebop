"""Chicken Run: a pot that grows every second and a bomb nobody can see.

Each round, after a short "get ready", the pot starts climbing: value(t) = 20 x 1.15^t points. Tap
CASH OUT to bank the value at the moment the server gets your tap. Somewhere between 4 and 24
seconds a hidden bomb goes off: anyone still in gets nothing. The round's biggest cash-out takes a
+50 bonus for nerve. Five rounds.

While everyone gets ready, two dirty tricks (paid for from this game's points):
- Insurance (30): if you blow up this round, you still get 25% of what the pot had reached.
- Short fuse (40, once a game): pick a rival. Their personal bomb goes off at a random 40-80% of the
  real one. They're told someone did it (not who); the culprit is named at the bang.

Taps are credited at the moment the player tapped (the client sends the time it showed), within a
short window: the claim can only be up to TAP_LAG seconds before the server got it, never after. So
phone lag doesn't cost points or turn an in-time tap into a boom, and nobody can claim more than lag.

Secrecy: the bomb time lives only here until it goes off. The run phase deliberately has no public
deadline (a countdown would give the bomb away); clients animate the value from `started_ago`.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar

from .base import Game, GameError

ROUNDS = 5
BASE, GROWTH = 20.0, 1.15
BOMB_MIN, BOMB_MAX = 4.0, 24.0
NERVE_BONUS = 50
INSURANCE_COST, INSURANCE_SHARE = 30, 0.25
FUSE_COST = 40
FUSE_MIN, FUSE_MAX = 0.4, 0.8
TAP_LAG = 0.4  # seconds: how far back a tap's own time may be credited (network + screen lag)


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
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "The pot climbs every second. Tap CASH OUT to bank what it's worth right then.",
        "A hidden bomb goes off somewhere between 4 and 24 seconds. Still in? You get nothing.",
        "Biggest cash-out of the round gets +50 for nerve.",
        "Before each run: buy insurance (keep 25% if you blow up), or once a game shorten a rival's fuse.",
    )
    READING: ClassVar[frozenset[str]] = frozenset(["boom", "ready"])

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"ready": 12.0, "boom": 10.0}

    def start(self) -> None:
        self.history: list[dict[str, Any]] = []
        self.fuse_used: set[str] = set()
        self.round = 0
        self._ready()

    def _ready(self) -> None:
        self.bomb = self.rng.uniform(BOMB_MIN, BOMB_MAX)  # seconds after the run starts: secret
        self.cashed: dict[str, dict[str, Any]] = {}  # pid -> {"t", "value"}
        self.run_start: float | None = None
        self.result: dict[str, Any] | None = None
        self.insured: set[str] = set()
        self.fuses: dict[str, float] = {}  # target -> personal bomb time (secret)
        self.saboteurs: dict[str, list[str]] = {}  # target -> who shortened it
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

    def bomb_for(self, pid: str) -> float:
        return self.fuses.get(pid, self.bomb)

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
        payouts = {
            p: int(value_at(round(self.bomb_for(p), 2)) * INSURANCE_SHARE)
            for p in boomed
            if p in self.insured
        }
        for pid, pts in payouts.items():
            self.add_points(pid, pts)
        # Costs were taken when bought; the record carries the net so anyone can check the total.
        extras = {p: payouts.get(p, 0) for p in self.player_ids}
        for p in self.insured:
            extras[p] -= INSURANCE_COST
        for subs in self.saboteurs.values():
            for p in subs:
                extras[p] -= FUSE_COST
        self.result = {
            "bomb": bomb,
            "bomb_value": value_at(bomb),
            "cashed": {p: dict(c) for p, c in self.cashed.items()},
            "boomed": boomed,
            "nerve": bonus,
            "insured": sorted(self.insured),
            "payouts": payouts,
            "fuses": {p: round(t, 2) for p, t in self.fuses.items()},
            "saboteurs": {p: list(v) for p, v in self.saboteurs.items()},
            "extras": extras,
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
        kind = action.get("a")
        if kind in ("insure", "fuse"):
            self._trick(pid, kind, action)
            return
        if kind != "cash":
            raise GameError("bad_action", "Unknown action")
        if self.phase != "run":
            raise GameError("wrong_phase", "Wait for the run")
        if pid in self.cashed:
            raise GameError("already_locked", "You already cashed out")
        now = self.elapsed()
        t = self._tap_time(action.get("at"), now)
        if t >= self.bomb_for(pid):
            if now >= self.bomb:
                self._end_round()  # the tap came after the bang: it goes off now
            short = pid in self.fuses and t < self.bomb
            raise GameError("too_late", "BOOM! Your fuse was short" if short else "BOOM! Too late")
        # Value the published (rounded) time, so anyone can check the number from the time shown.
        self.cashed[pid] = {"t": t, "value": value_at(t)}
        self.bump()
        if len(self.cashed) == len(self.players) or now >= self.bomb:
            self._end_round()

    @staticmethod
    def _tap_time(claim: Any, now: float) -> float:
        """When the player tapped: their own claim, kept within [now - TAP_LAG, now]; else now."""
        if claim is None:
            return round(now, 2)
        if isinstance(claim, bool) or not isinstance(claim, int | float) or not math.isfinite(claim):
            raise GameError("bad_input", "Tap time must be a number")
        return round(min(now, max(float(claim), now - TAP_LAG)), 2)

    def _trick(self, pid: str, kind: str, action: dict[str, Any]) -> None:
        if self.phase != "ready":
            raise GameError("wrong_phase", "Tricks only before the run starts")
        if kind == "insure":
            if pid in self.insured:
                raise GameError("already_locked", "You're already insured")
            self.insured.add(pid)
            self.add_points(pid, -INSURANCE_COST)
        else:
            target = action.get("target")
            if not isinstance(target, str) or target == pid or target not in self.round_scores:
                raise GameError("bad_target", "Pick a rival")
            if pid in self.fuse_used:
                raise GameError("already_used", "One short fuse per game")
            self.fuse_used.add(pid)
            self.add_points(pid, -FUSE_COST)
            fuse = self.bomb * self.rng.uniform(FUSE_MIN, FUSE_MAX)
            self.fuses[target] = min(fuse, self.fuses.get(target, self.bomb))
            self.saboteurs.setdefault(target, []).append(pid)
        self.bump()

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
            "insured": sorted(self.insured),  # public: everyone can see who's nervous
            "costs": {"insure": INSURANCE_COST, "fuse": FUSE_COST},
            "you": {
                "fused": pid in self.fuses,  # someone shortened your fuse (never who, never when)
                "fuse_used": pid in self.fuse_used,
            },
        }
        if self.phase in ("boom", "final") and self.result:
            view["result"] = self.result  # the bomb time, only once it has gone off
        if self.phase == "final":
            view["history"] = self.history
        return view

    def peek(self, pid: str) -> str | None:
        """Power card: a safe window. Your bomb is somewhere after this."""
        if self.phase not in ("ready", "run") or self.finished:
            return None
        safe = max(BOMB_MIN, int(self.bomb_for(pid) * 0.75))
        return f"Your bomb won't go off before {safe:g} seconds this round."

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
