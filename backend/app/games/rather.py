"""Would You Rather: the hot seat. How well do your friends really know you?

Each round one player is in the hot seat and everyone gets the same dilemma ("Would you rather fly or be
invisible?"). Everyone answers it, and everyone but the hot seat also guesses what the hot seat chose.
The reveal shows how the room split, the hot seat's answer, and who read them right. A right guess is
worth 100; the hot seat gets 50 for every friend who read them right. Everyone takes the hot seat once
(or twice, with two laps).

Secrecy: answers and guesses stay hidden until the reveal (only who has locked in is shown). A host
can't skip a running round: the clock or the last answer ends it.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError, as_int
from .content import RATHER

GUESS_POINTS = 100
KNOWN_POINTS = 50  # to the hot seat, per right guess


class WouldYouRather(Game):
    game_id: ClassVar[str] = "rather"
    title: ClassVar[str] = "Would You Rather"
    blurb: ClassVar[str] = (
        "Fly or be invisible? Everyone answers, then guesses what the friend in the hot seat picked. "
        "How well do you really know each other?"
    )
    min_players: ClassVar[int] = 3
    max_players: ClassVar[int] = 8
    OPTIONS: ClassVar[dict[str, list[str]]] = {"laps": ["1", "2"]}
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Each round, one player is in the hot seat. Everyone gets the same Would You Rather.",
        "Pick your own answer, then guess what the hot seat picked.",
        "Right guess: 100. The hot seat gets 50 for every friend who read them right.",
        "Everyone takes the hot seat once (twice with two laps).",
    )
    READING: ClassVar[frozenset[str]] = frozenset(["reveal"])

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"pick": 30.0, "reveal": 10.0}

    def start(self) -> None:
        self.order = list(self.player_ids)
        self.rng.shuffle(self.order)
        self.rounds = len(self.order) * int(self.options.get("laps", "1"))
        self.dilemmas = [RATHER[i] for i in self.deal("dilemmas", len(RATHER), self.rounds, kind="rather")]
        self.history: list[dict[str, Any]] = []
        self.round = 0
        self._ask()

    @property
    def hot(self) -> str:
        return self.order[self.round % len(self.order)]

    def _ask(self) -> None:
        self.picks: dict[str, int] = {}
        self.guesses: dict[str, int] = {}
        self.result: dict[str, Any] | None = None
        self.phase = "pick"
        self.set_deadline(self.timings["pick"])
        self.bump()

    def _locked(self, pid: str) -> bool:
        return pid in self.picks and (pid == self.hot or pid in self.guesses)

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        if action.get("a") != "answer":
            raise GameError("bad_action", "Unknown action")
        if self.phase != "pick":
            raise GameError("wrong_phase", "Answers are closed")
        if self._locked(pid):
            raise GameError("already_locked", "You're locked in")
        pick = as_int(action.get("pick"), lo=0, hi=1, field="Your answer")
        guess = None
        if pid != self.hot:
            guess = as_int(action.get("guess"), lo=0, hi=1, field="Your guess")
        self.picks[pid] = pick
        if guess is not None:
            self.guesses[pid] = guess
        self.bump()
        if all(self._locked(p) for p in self.player_ids):
            self._reveal()

    def _reveal(self) -> None:
        hot = self.hot
        theirs = self.picks.get(hot)  # None: the hot seat didn't answer in time, so no guess can be right
        right = sorted(p for p, g in self.guesses.items() if theirs is not None and g == theirs)
        gains = {p: 0 for p in self.player_ids}
        for p in right:
            gains[p] += GUESS_POINTS
        gains[hot] += KNOWN_POINTS * len(right)
        for p, g in gains.items():
            self.add_points(p, g)
        d = self.dilemmas[self.round]
        self.result = {
            "hot": hot,
            "choice": theirs,
            "picks": dict(self.picks),
            "guesses": dict(self.guesses),
            "right": right,
            "gains": gains,
            "split": [sum(1 for v in self.picks.values() if v == side) for side in (0, 1)],
        }
        self.history.append({"a": d["a"], "b": d["b"], **self.result})
        self.phase = "reveal"
        self.set_deadline(self.timings["reveal"])
        self.bump()

    def _next(self) -> None:
        if self.round + 1 >= self.rounds:
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
            return
        self.round += 1
        self._ask()

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

    def skip(self) -> bool:
        """The reveal only: skipping a running round would cut short whoever is still deciding."""
        if self.phase == "pick":
            return False
        self.advance()
        return True

    POWERS: ClassVar[dict[str, dict[str, str]]] = {
        "rather_room": {
            "name": "Ask the room",
            "icon": "🗳️",
            "text": "See which way everyone else is leaning",
        },
    }

    def use_power(self, pid: str, item: str) -> str | None:
        if item != "rather_room":
            return super().use_power(pid, item)
        if self.phase != "pick" or pid == self.hot or pid in self.guesses:
            raise GameError("not_now", "Use it while you're guessing, before you lock in")
        line = self.peek(pid)
        if line is None:
            raise GameError("not_now", "Nobody else has answered yet: try again in a moment")
        return line

    def peek(self, pid: str) -> str | None:
        """Power card: which way the room is leaning so far (never the hot seat's own answer)."""
        if self.phase != "pick" or pid == self.hot:
            return None
        votes = [v for p, v in self.picks.items() if p not in (pid, self.hot)]
        if not votes:
            return None
        d = self.dilemmas[self.round]
        a = votes.count(0)
        lean = d["a"] if a > len(votes) - a else d["b"] if a < len(votes) - a else None
        return f"So far the room leans to “{lean}”." if lean else "So far the room is split down the middle."

    def view_for(self, pid: str) -> dict[str, Any]:
        d = self.dilemmas[min(self.round, self.rounds - 1)]
        seated = pid in self.round_scores
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": self.rounds,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "hot": self.hot,
            "dilemma": {"a": d["a"], "b": d["b"]},
            "locked": sorted(p for p in self.player_ids if self._locked(p)) if self.phase == "pick" else [],
            "scores": self.scores(),
            "you": {"pick": self.picks.get(pid), "guess": self.guesses.get(pid), "hot": pid == self.hot}
            if seated
            else None,
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
        reads: dict[str, int] = {}
        for h in self.history:
            for p in h["right"]:
                reads[p] = reads.get(p, 0) + 1
        if reads:
            p, n = max(reads.items(), key=lambda x: x[1])
            out.append(
                {"icon": "🔮", "title": "Mind reader", "text": f"{self.name_of(p)} read {n} friends right"}
            )
        known = max(self.history, key=lambda h: len(h["right"]), default=None)
        if known and known["right"]:
            out.append(
                {
                    "icon": "📖",
                    "title": "Open book",
                    "text": f"{len(known['right'])} friends knew {self.name_of(known['hot'])} would rather "
                    f"{known['a'] if known['choice'] == 0 else known['b']}",
                }
            )
        wild = next(
            (h for h in self.history if h["choice"] is not None and h["guesses"] and not h["right"]), None
        )
        if wild:
            out.append(
                {
                    "icon": "🃏",
                    "title": "Wild card",
                    "text": f"Nobody guessed {self.name_of(wild['hot'])} would rather "
                    f"{wild['a'] if wild['choice'] == 0 else wild['b']}",
                }
            )
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "rounds": len(self.history)}
