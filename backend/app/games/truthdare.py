"""Truth or Dare: spin the bottle, pick your poison, let the room judge.

Turns: the bottle spins and lands on someone. Everyone gets the same number of turns (the order is a
fresh shuffle each lap, never the same person twice in a row across laps). They choose TRUTH or DARE;
the prompt card is dealt from the room's no-repeat deck and shown to everyone. They answer or do it,
tap Done, and the rest of the room votes: nailed it, or weak? A majority of 👍 (ties count as 👍)
pays 100 for a truth and 200 for a dare.

Twists: once per game each player may re-roll their prompt (same kind) or chicken out (no points, and
the room will remember). Three dares in a row is a Daredevil streak: +100 on the third and every one
after. The host picks the heat (mild, or cheeky: bold and embarrassing, never sexual) and the length.

Nothing is typed: prompts come from the built-in pools. Votes stay secret (a count only) until the
result; nothing else here is hidden.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError
from .content import TOD_DARES, TOD_TRUTHS

POINTS = {"truth": 100, "dare": 200}
STREAK = 3  # dares in a row for the Daredevil bonus
STREAK_BONUS = 100
TURNS = {"standard": 2, "quick": 1, "marathon": 3}  # turns per player


class TruthOrDare(Game):
    game_id: ClassVar[str] = "truthdare"
    title: ClassVar[str] = "Truth or Dare"
    blurb: ClassVar[str] = (
        "Spin the bottle. Truth or dare? Do it, and the room votes if you really nailed it. "
        "Dares pay double, chickens pay nothing."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True
    OPTIONS: ClassVar[dict[str, list[str]]] = {
        "heat": ["mild", "cheeky"],
        "length": ["standard", "quick", "marathon"],
    }
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "The bottle spins and picks whose turn it is. Everyone gets the same number of turns.",
        "Pick TRUTH (answer honestly, out loud) or DARE (do it right now). Everyone sees the card.",
        "Tap Done when you have. Everyone else votes: 👍 nailed it or 👎 weak.",
        "Mostly 👍? Truths pay 100, dares pay 200. Three dares in a row: +100 Daredevil bonus.",
        "Once per game you can re-roll a card you hate, or chicken out (no points, no shame... some shame).",
    )
    READING: ClassVar[frozenset[str]] = frozenset({"result"})

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"spin": 5.0, "choose": 20.0, "truth": 60.0, "dare": 90.0, "vote": 15.0, "result": 8.0}

    def start(self) -> None:
        self.heat = self.options.get("heat", "mild")
        if self.heat not in TOD_TRUTHS:
            self.heat = "mild"
        per = TURNS.get(self.options.get("length", "standard"), TURNS["standard"])
        self.order: list[str] = []
        for _ in range(per):
            lap = list(self.player_ids)
            self.rng.shuffle(lap)
            if self.order and len(lap) > 1 and lap[0] == self.order[-1]:
                lap.append(lap.pop(0))  # nobody goes twice in a row across laps
            self.order.extend(lap)
        self.turn = -1
        self.stats: dict[str, dict[str, int]] = {
            p: {"truth": 0, "dare": 0, "chicken": 0, "likes": 0, "streak": 0, "points": 0}
            for p in self.player_ids
        }
        self.rerolls: dict[str, int] = dict.fromkeys(self.player_ids, 1)
        self.chickens: dict[str, int] = dict.fromkeys(self.player_ids, 1)
        self.history: list[dict[str, Any]] = []
        self._next_turn()

    # -- turn flow ----------------------------------------------------------------------------------
    @property
    def target(self) -> str:
        return self.order[self.turn]

    def _next_turn(self) -> None:
        if self.turn + 1 >= len(self.order):  # the turn index stays on the last turn: target stays valid
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
            return
        self.turn += 1
        self.round = self.turn
        self.choice: str | None = None
        self.prompt: str = ""
        self.votes: dict[str, bool] = {}
        self.done = False
        self.result: dict[str, Any] | None = None
        self.phase = "spin"
        self.set_deadline(self.timings["spin"])
        self.bump()

    def _deal(self, kind: str) -> str:
        pool = (TOD_TRUTHS if kind == "truth" else TOD_DARES)[self.heat]
        return pool[self.deal(f"{kind}-{self.heat}", len(pool), 1)[0]]

    def _choose(self, kind: str) -> None:
        self.choice = kind
        self.prompt = self._deal(kind)
        self.phase = "perform"
        self.set_deadline(self.timings[kind])
        self.bump()

    def _voters(self) -> list[str]:
        return [p for p in self.player_ids if p != self.target]

    def _open_vote(self) -> None:
        self.done = True
        self.phase = "vote"
        self.set_deadline(self.timings["vote"])
        self.bump()

    def _settle(self, chicken: bool = False) -> None:
        pid, kind = self.target, self.choice or "truth"
        s = self.stats[pid]
        yes = sum(self.votes.values())
        no = len(self.votes) - yes
        passed = not chicken and yes >= no
        points = bonus = 0
        if chicken:
            s["chicken"] += 1
            s["streak"] = 0
        else:
            s[kind] += 1
            s["likes"] += yes
            s["streak"] = s["streak"] + 1 if kind == "dare" else 0
            if passed:
                points = POINTS[kind]
                if kind == "dare" and s["streak"] >= STREAK:
                    bonus = STREAK_BONUS
        self.add_points(pid, points + bonus)
        s["points"] += points + bonus
        self.result = {
            "player": pid,
            "kind": kind,
            "prompt": self.prompt,
            "chicken": chicken,
            "yes": yes,
            "no": no,
            "passed": passed,
            "points": points,
            "bonus": bonus,
        }
        self.history.append(self.result)
        self.phase = "result"
        self.set_deadline(self.timings["result"])
        self.bump()

    # -- actions ------------------------------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        if self.finished:
            raise GameError("wrong_phase", "The game is over")
        if kind == "vote":
            self._vote(pid, action)
            return
        if pid != self.target:
            raise GameError("not_your_turn", "It's not your turn")
        if kind == "choose" and self.phase == "choose":
            choice = action.get("choice")
            if choice not in POINTS:
                raise GameError("bad_input", "Truth or dare?")
            self._choose(choice)
        elif kind == "done" and self.phase == "perform":
            if len(self._voters()) == 0:
                self._settle()
            else:
                self._open_vote()
        elif kind == "reroll" and self.phase == "perform":
            if self.rerolls[pid] <= 0:
                raise GameError("no_rerolls", "You've used your re-roll")
            self.rerolls[pid] -= 1
            self.prompt = self._deal(self.choice or "truth")
            self.set_deadline(self.timings[self.choice or "truth"])
            self.bump()
        elif kind == "chicken" and self.phase == "perform":
            if self.chickens[pid] <= 0:
                raise GameError("no_chickens", "No chickening out twice!")
            self.chickens[pid] -= 1
            self._settle(chicken=True)
        elif kind in ("choose", "done", "reroll", "chicken"):
            raise GameError("wrong_phase", "Not right now")
        else:
            raise GameError("bad_action", "Unknown action")

    def _vote(self, pid: str, action: dict[str, Any]) -> None:
        if self.phase != "vote":
            raise GameError("wrong_phase", "Voting isn't open")
        if pid == self.target:
            raise GameError("no_self_vote", "You can't judge yourself!")
        like = action.get("like")
        if not isinstance(like, bool):
            raise GameError("bad_input", "Thumbs up or down?")
        self.votes[pid] = like
        self.bump()
        if set(self._voters()) <= set(self.votes):
            self._settle()

    # -- clocks -------------------------------------------------------------------------------------
    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        """Timer or host. A silent chooser gets a random pick; a performer out of time goes to the vote."""
        if self.finished:
            return
        if self.phase == "spin":
            self.phase = "choose"
            self.set_deadline(self.timings["choose"])
            self.bump()
        elif self.phase == "choose":
            self._choose(self.rng.choice(sorted(POINTS)))
        elif self.phase == "perform":
            if self._voters():
                self._open_vote()
            else:
                self._settle()
        elif self.phase == "vote":
            self._settle()
        elif self.phase == "result":
            self._next_turn()

    # -- views --------------------------------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        playing = not self.finished
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.turn + 1,
            "rounds": len(self.order),
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "heat": self.heat,
            "target": self.target if playing else None,
            "choice": self.choice if playing else None,
            "prompt": self.prompt if playing and self.phase in ("perform", "vote", "result") else "",
            "voted": len(self.votes) if playing else 0,
            "voters": len(self._voters()),
            "you_voted": self.votes.get(pid) if playing else None,
            "rerolls": dict(self.rerolls),
            "chickens": dict(self.chickens),
            "stats": {p: dict(s) for p, s in self.stats.items()},
            "result": self.result if self.phase == "result" else None,
            "up_next": self.order[self.turn + 1] if self.turn + 1 < len(self.order) else None,
        }
        if self.finished:
            view["history"] = self.history
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        out: list[dict[str, str]] = []

        def most(key: str) -> tuple[str, int] | None:
            best = max(self.player_ids, key=lambda p: self.stats[p][key], default=None)
            return (best, self.stats[best][key]) if best and self.stats[best][key] > 0 else None

        if top := most("dare"):
            out.append(
                {"icon": "🔥", "title": "Daredevil", "text": f"{self.name_of(top[0])} took {top[1]} dares"}
            )
        if top := most("truth"):
            out.append(
                {"icon": "📖", "title": "Open book", "text": f"{self.name_of(top[0])} told {top[1]} truths"}
            )
        if top := most("likes"):
            out.append(
                {
                    "icon": "👍",
                    "title": "Crowd pleaser",
                    "text": f"{self.name_of(top[0])} earned {top[1]} thumbs up",
                }
            )
        if top := most("chicken"):
            out.append({"icon": "🐔", "title": "Bawk bawk", "text": f"{self.name_of(top[0])} chickened out"})
        return out

    def summary(self) -> dict[str, Any]:
        return {
            "players": len(self.players),
            "heat": self.heat,
            "dares": sum(1 for h in self.history if h["kind"] == "dare" and not h["chicken"]),
            "truths": sum(1 for h in self.history if h["kind"] == "truth" and not h["chicken"]),
            "chickens": sum(1 for h in self.history if h["chicken"]),
        }
