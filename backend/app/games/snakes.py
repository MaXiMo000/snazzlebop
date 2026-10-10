"""Snakes and Ladders: roll, climb, slide, first to 100.

One token each on the classic 10 x 10 board. Roll the die and move; land at the foot of a ladder and
climb it, land on a snake's head and slide down to its tail. A six rolls again (three sixes in a row and
the turn passes). You need the exact number to land on 100: roll too much and you stay put. The first
player home wins; everyone else scores by how far they got.

Nothing is hidden: the die is rolled on the server and every screen sees the same board.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError

LAST = 100
LADDERS = {2: 38, 7: 14, 8: 31, 15: 26, 21: 42, 28: 84, 36: 44, 51: 67, 71: 91, 78: 98, 87: 94}
SNAKES = {16: 6, 46: 25, 49: 11, 62: 19, 64: 60, 74: 53, 89: 68, 92: 88, 95: 75, 99: 80}
JUMPS = {**LADDERS, **SNAKES}
WIN, PER_SQUARE = 500, 3
KEEP_LOG = 8
LAND_SECONDS = 1.2  # the token's walk on every screen; the next roll waits for it


class SnakesAndLadders(Game):
    game_id: ClassVar[str] = "snakes"
    title: ClassVar[str] = "Snakes and Ladders"
    blurb: ClassVar[str] = (
        "Roll and race to 100. Ladders shoot you up, snakes send you sliding back down. "
        "Pure luck, loud groans."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Take turns rolling the die and move your token that many squares.",
        "Land at the foot of a ladder: climb it. Land on a snake's head: slide down to its tail.",
        "Roll a 6 and you roll again. Three 6s in a row and your turn is over.",
        "You need the exact number to land on 100. First one home wins.",
    )
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True
    TEAMS: ClassVar[bool] = True

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"turn": 15.0}

    def start(self) -> None:
        self.order = list(self.player_ids)
        self.rng.shuffle(self.order)
        self.pos: dict[str, int] = dict.fromkeys(self.order, 0)  # 0 = not on the board yet
        self.turn = 0
        self.sixes = 0
        self.last: dict[str, Any] | None = None
        self.log: list[dict[str, Any]] = []
        self.moves = 0
        self.stats: dict[str, dict[str, int]] = {p: {"ladders": 0, "snakes": 0} for p in self.order}
        self.winner: str | None = None
        self.ready_at = 0.0
        self.phase = "play"
        self.set_deadline(self.timings["turn"])
        self.bump()

    @property
    def current(self) -> str:
        return self.order[self.turn]

    @property
    def stage(self) -> str:
        return f"{self.phase}:{self.moves}"

    def _roll(self) -> None:
        pid = self.current
        die = self.rng.randint(1, 6)
        start = self.pos[pid]
        mid = start + die if start + die <= LAST else start  # too much: stay where you are
        end = JUMPS.get(mid, mid)
        via = (
            "ladder"
            if mid in LADDERS and mid != start
            else "snake"
            if mid in SNAKES and mid != start
            else None
        )
        if via is None:
            end = mid
        else:
            self.stats[pid]["ladders" if via == "ladder" else "snakes"] += 1
        self.pos[pid] = end
        self.moves += 1
        self.round = self.moves
        self.last = {
            "n": self.moves,
            "player": pid,
            "die": die,
            "from": start,
            "mid": mid,
            "to": end,
            "via": via,
        }
        self.log = [*self.log, self.last][-KEEP_LOG:]
        if end == LAST:
            self.winner = pid
            self.add_points(pid, WIN)
            for p, at in self.pos.items():
                if p != pid:
                    self.add_points(p, at * PER_SQUARE)
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
            return
        self.sixes = self.sixes + 1 if die == 6 else 0
        if die != 6 or self.sixes >= 3:
            self.turn = (self.turn + 1) % len(self.order)
            self.sixes = 0
        self.ready_at = self.clock() + LAND_SECONDS
        self.set_deadline(self.timings["turn"])
        self.bump()

    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        if action.get("a") != "roll":
            raise GameError("bad_action", "Unknown action")
        if self.phase != "play":
            raise GameError("wrong_phase", "The game is over")
        if pid != self.current:
            raise GameError("not_your_turn", "It isn't your turn")
        if self.clock() < self.ready_at:
            raise GameError("wait", "Let the last token land")
        self._roll()

    def tick(self) -> None:
        if not self.finished and self.expired():
            self._roll()  # ran out of time: the die is rolled for them

    def advance(self) -> None:
        if not self.finished:
            self._roll()

    def view_for(self, pid: str) -> dict[str, Any]:
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.moves,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "order": list(self.order),
            "pos": dict(self.pos),
            "turn": self.current if self.phase == "play" else None,
            "sixes": self.sixes,
            "last": self.last,
            "log": self.log,
            "ladders": [[a, b] for a, b in LADDERS.items()],
            "snakes": [[a, b] for a, b in SNAKES.items()],
            "winner": self.winner,
        }
        if self.phase == "final":
            view["scores"] = self.scores()
            view["stats"] = self.stats
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished or self.winner is None:
            return []
        out = [{"icon": "🏁", "title": "Home first", "text": f"{self.name_of(self.winner)} reached 100"}]
        bitten = max(self.stats.items(), key=lambda kv: kv[1]["snakes"])
        if bitten[1]["snakes"] >= 2:
            out.append(
                {
                    "icon": "🐍",
                    "title": "Snake charmer",
                    "text": f"{self.name_of(bitten[0])} slid {bitten[1]['snakes']} times",
                }
            )
        climber = max(self.stats.items(), key=lambda kv: kv[1]["ladders"])
        if climber[1]["ladders"] >= 2:
            out.append(
                {
                    "icon": "🪜",
                    "title": "Social climber",
                    "text": f"{self.name_of(climber[0])} climbed {climber[1]['ladders']} ladders",
                }
            )
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "moves": self.moves}
