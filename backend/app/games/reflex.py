"""Reaction Duel: wait... wait... TAP!

Every round the big pad says "Wait..." for a random few seconds, then "TAP!". Fastest tap wins the
round. In between, fake-outs flash up: look-alike words such as "TAB!" or "TRAP!" in bright colours. Tap
on anything but the real TAP! and you're out of that round and lose points.

The moment of the real signal and of each fake-out is decided on the server and never sent ahead of time:
a screen only learns what to show when it's time to show it. Reaction times are measured on the server
from the signal to the tap arriving.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError

FAKES = ("TAB!", "TOP!", "TIP!", "NAP!", "TAP?", "TRAP!", "PAT!", "WAIT!", "TAPE!", "ZAP!")
TONES = 4  # colours a fake-out can flash in (the real signal is always green)
PLACE_POINTS = (100, 60, 40)
TAPPED, EARLY = 20, -50
FAKE_SECONDS = 0.8


class ReactionDuel(Game):
    game_id: ClassVar[str] = "reflex"
    title: ClassVar[str] = "Reaction Duel"
    blurb: ClassVar[str] = (
        "Wait… wait… TAP! Fastest finger wins the round. "
        "Fall for a fake-out like TAB! or TRAP! and you're out of it."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8
    OPTIONS: ClassVar[dict[str, list[str]]] = {"rounds": ["7", "5", "10"]}
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Everyone gets a big pad. It says “Wait…” for a few seconds.",
        "When it says TAP! in green, hit it. Fastest wins 100, then 60, then 40.",
        "Watch out for fake-outs: TAB!, TRAP!, TAP? and friends. Only the exact word TAP! counts.",
        "Tap early or on a fake and you lose 50 and sit out that round.",
    )
    READING: ClassVar[frozenset[str]] = frozenset(["result"])
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"wait_min": 2.5, "wait_max": 7.0, "go": 3.0, "result": 7.0}

    def start(self) -> None:
        self.rounds = int(self.options.get("rounds", "7"))
        self.history: list[dict[str, Any]] = []
        self.best: dict[str, float] = {}  # each player's fastest tap, in seconds
        self.round = 0
        self._begin()

    def _begin(self) -> None:
        self.round += 1
        now = self.clock()
        self.go_at = now + self.rng.uniform(self.timings["wait_min"], self.timings["wait_max"])
        # Up to two fake-outs, none in the last moment before the real thing.
        self.fakes: list[tuple[float, str, int]] = []
        t = now + self.rng.uniform(0.9, 1.8)
        while t + FAKE_SECONDS + 0.5 < self.go_at and len(self.fakes) < 2:
            if self.rng.random() < 0.75:
                self.fakes.append((t, self.rng.choice(FAKES), self.rng.randrange(TONES)))
            t += FAKE_SECONDS + self.rng.uniform(0.6, 1.6)
        self.fake: dict[str, Any] | None = None  # the fake-out on screen right now
        self.fake_no = 0
        self.early: list[str] = []
        self.taps: dict[str, float] = {}  # player -> seconds after the signal
        self.result: dict[str, Any] | None = None
        self.phase = "wait"
        self.deadline = None  # nothing to count down to: the signal is a surprise
        self.bump()

    def _waiting(self) -> list[str]:
        return [p for p in self.player_ids if p not in self.early and p not in self.taps]

    def _settle(self) -> None:
        ranked = sorted(self.taps, key=lambda p: self.taps[p])
        points: dict[str, int] = {}
        for i, pid in enumerate(ranked):
            points[pid] = PLACE_POINTS[i] if i < len(PLACE_POINTS) else TAPPED
            self.best[pid] = min(self.best.get(pid, 9e9), self.taps[pid])
        for pid in self.early:
            points[pid] = EARLY
        for pid, pts in points.items():
            self.add_points(pid, pts)
        self.result = {
            "times": {p: round(self.taps[p] * 1000) for p in ranked},  # milliseconds, fastest first
            "early": list(self.early),
            "points": points,
            "winner": ranked[0] if ranked else None,
        }
        self.history.append(self.result)
        self.fake = None
        self.phase = "result"
        self.set_deadline(self.timings["result"])
        self.bump()

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        if action.get("a") != "tap":
            raise GameError("bad_action", "Unknown action")
        if self.phase not in ("wait", "go"):
            raise GameError("wrong_phase", "Wait for the next round")
        if pid in self.early or pid in self.taps:
            raise GameError("already", "You've already tapped this round")
        if self.phase == "wait":
            self.early.append(pid)
        else:
            self.taps[pid] = max(0.0, self.clock() - self.go_time)
        self.bump()
        if not self._waiting():
            self._settle()

    def tick(self) -> None:
        if self.finished:
            return
        now = self.clock()
        if self.phase == "wait":
            if now >= self.go_at:
                self.fake = None
                self.go_time = now  # measured from when the screens are actually told
                self.phase = "go"
                self.set_deadline(self.timings["go"])
                self.bump()
                return
            due = next(((t, w, c) for t, w, c in self.fakes if t <= now < t + FAKE_SECONDS), None)
            shown = (self.fake or {}).get("at")
            if due is None and self.fake is not None:
                self.fake = None
                self.bump()
            elif due is not None and shown != due[0]:
                self.fake_no += 1
                self.fake = {"at": due[0], "word": due[1], "tone": due[2], "n": self.fake_no}
                self.bump()
        elif self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "wait":
            self.go_at = self.clock()  # the host skipped the wait: the signal comes now
            self.tick()
        elif self.phase == "go":
            self._settle()
        elif self.round >= self.rounds:
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
        else:
            self._begin()

    def view_for(self, pid: str) -> dict[str, Any]:
        """What's on the pad right now. When the signal or a fake-out will come is never in here."""
        fake = self.fake if self.phase == "wait" else None
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round,
            "rounds": self.rounds,
            "remaining": self.remaining() if self.phase == "result" else None,
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "fake": {"word": fake["word"], "tone": fake["tone"], "n": fake["n"]} if fake else None,
            "early": list(self.early),  # public at once: everyone enjoys a false start
            "tapped": sorted(self.taps),  # who has tapped, not how fast (that's the result)
            "result": self.result if self.phase in ("result", "final") else None,
            "scores": self.scores(),
            "you": {"early": pid in self.early, "tapped": pid in self.taps}
            if pid in self.round_scores
            else None,
        }
        if self.phase == "final":
            view["best"] = {p: round(t * 1000) for p, t in self.best.items()}
            view["wins"] = {p.id: sum(1 for h in self.history if h["winner"] == p.id) for p in self.players}
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []
        if self.best:
            pid, t = min(self.best.items(), key=lambda kv: kv[1])
            out.append(
                {
                    "icon": "⚡",
                    "title": "Lightning",
                    "text": f"{self.name_of(pid)} tapped in {round(t * 1000)} ms",
                }
            )
        jumps: dict[str, int] = {}
        for h in self.history:
            for pid in h["early"]:
                jumps[pid] = jumps.get(pid, 0) + 1
        if jumps:
            pid, n = max(jumps.items(), key=lambda kv: kv[1])
            if n >= 2:
                out.append(
                    {"icon": "🙈", "title": "Jumpy", "text": f"{self.name_of(pid)} fell for it {n} times"}
                )
        return out

    def summary(self) -> dict[str, Any]:
        best = min(self.best.values(), default=0.0)
        return {"players": len(self.players), "rounds": self.rounds, "best_ms": round(best * 1000)}
