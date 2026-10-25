"""Battleships: two hidden fleets, one shot at a time.

Two sides: one player each, or two teams that share a fleet and take turns at the guns. Each side's
ships start at random on an 8 x 8 grid; move and turn them (or reshuffle) until you like it, then lock
in. Sides then fire
at each other's waters: a hit earns another shot, a miss passes the turn. Sink every ship to win.

A fleet's layout lives on the server and is sent only to its own side. The other side (and the TV and
the audience) see shots and their results, and a ship's shape only once it has been sunk.
"""

from __future__ import annotations

import random
from typing import Any, ClassVar

from .base import Game, GameError, as_int

SIZE = 8
FLEET = (4, 3, 3, 2, 2)
SIDE_NAMES = ("Fleet Tangerine", "Fleet Teal")
HIT, SINK, WIN = 50, 100, 300


def ship_cells(start: int, length: int, across: bool) -> list[int] | None:
    """The squares of a ship whose top-left square is `start`, or None if it would leave the grid."""
    row, col = divmod(start, SIZE)
    if (col + length if across else row + length) > SIZE:
        return None
    return [start + (i if across else i * SIZE) for i in range(length)]


def place(rng: random.Random) -> list[list[int]]:
    """A random legal layout: ships in straight lines, inside the grid, never overlapping."""
    taken: set[int] = set()
    ships: list[list[int]] = []
    for length in FLEET:
        while True:
            cells = ship_cells(rng.randrange(SIZE * SIZE), length, rng.random() < 0.5)
            if cells is not None and not taken & set(cells):
                taken |= set(cells)
                ships.append(cells)
                break
    return ships


class Battleships(Game):
    game_id: ClassVar[str] = "ships"
    title: ClassVar[str] = "Battleships"
    blurb: ClassVar[str] = (
        "Two hidden fleets. Call your shots, hear the splash or the boom, and sink them all first. "
        "One against one, or two teams sharing the guns."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Two sides, each with five hidden ships. With more than two players you share a fleet as a team.",
        "First, place your fleet: tap a ship, then tap where it should go (or turn it, or shuffle). Lock in.",
        "Take turns firing at the enemy's waters. Hit: fire again. Miss: the other side fires.",
        "A sunk ship shows its outline. Sink all five to win.",
    )
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"place": 75.0, "turn": 20.0}

    # -- setup ----------------------------------------------------------------------------------------
    def start(self) -> None:
        ids = list(self.player_ids)
        self.rng.shuffle(ids)
        half = (len(ids) + 1) // 2
        self.sides: list[list[str]] = [ids[:half], ids[half:]]
        self.side_of: dict[str, int] = {p: s for s, members in enumerate(self.sides) for p in members}
        self.fleets: list[list[list[int]]] = [place(self.rng), place(self.rng)]
        self.shots: list[dict[int, str]] = [{}, {}]  # shots each side has TAKEN: cell -> "hit" | "miss"
        self.ready = [False, False]
        self.gunner = [0, 0]  # whose turn within each side
        self.turn = self.rng.randrange(2)
        self.last: dict[str, Any] | None = None
        self.shot_no = 0
        self.winner: int | None = None
        self.tally: dict[str, dict[str, int]] = {p: {"hits": 0, "sunk": 0, "shots": 0} for p in ids}
        self.phase = "place"
        self.set_deadline(self.timings["place"])
        self.bump()

    @property
    def stage(self) -> str:
        return f"{self.phase}:{self.shot_no}"

    def _shooter(self) -> str:
        members = self.sides[self.turn]
        return members[self.gunner[self.turn] % len(members)]

    def _sunk(self, side: int) -> list[list[int]]:
        return [ship for ship in self.fleets[side] if all(c in self.shots[side] for c in ship)]

    def _battle(self) -> None:
        self.ready = [True, True]
        self.phase = "battle"
        self.set_deadline(self.timings["turn"])
        self.bump()

    POWERS: ClassVar[dict[str, dict[str, str]]] = {
        "ships_sonar": {
            "name": "Sonar ping",
            "icon": "📡",
            "text": "How many ship squares hide in a patch of their sea",
        },
    }

    def use_power(self, pid: str, item: str) -> str | None:
        if item != "ships_sonar":
            return super().use_power(pid, item)
        if self.phase != "battle" or pid not in self.side_of:
            raise GameError("not_now", "Use it once the battle has started")
        side = self.side_of[pid]
        tried = self.shots[side]
        fresh = [c for c in range(SIZE * SIZE) if c not in tried]
        if not fresh:
            raise GameError("not_now", "There's no unexplored water left")
        centre = self.rng.choice(fresh)
        r, c = divmod(centre, SIZE)
        r, c = min(max(r, 1), SIZE - 2), min(max(c, 1), SIZE - 2)  # keep the 3x3 patch on the board
        patch = {(r + dr) * SIZE + (c + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)}
        ships = {cell for ship in self.fleets[1 - side] for cell in ship}
        found = len((patch & ships) - set(tried))
        where = f"{'ABCDEFGH'[r - 1]}{c}-{'ABCDEFGH'[r + 1]}{c + 2}"
        noun = "square" if found == 1 else "squares"
        return f"Sonar: {found} unfound ship {noun} in {where}."

    def _fire(self, pid: str, cell: int) -> None:
        target = 1 - self.turn
        ship = next((s for s in self.fleets[target] if cell in s), None)
        self.shots[target][cell] = "hit" if ship else "miss"
        self.shot_no += 1
        self.round = self.shot_no
        self.tally[pid]["shots"] += 1
        result = "miss"
        if ship:
            result = "hit"
            self.tally[pid]["hits"] += 1
            self.add_points(pid, HIT)
            if all(c in self.shots[target] for c in ship):
                result = "sunk"
                self.tally[pid]["sunk"] += 1
                self.add_points(pid, SINK)
        self.last = {"n": self.shot_no, "by": pid, "side": target, "cell": cell, "result": result}
        if len(self._sunk(target)) == len(FLEET):
            self.winner = self.turn
            for member in self.sides[self.turn]:
                self.add_points(member, WIN)
            self.phase = "final"
            self.deadline = None
            self.finished = True
            self.bump()
            return
        self.gunner[self.turn] += 1  # the next gun on this side, whenever its turn comes
        if result == "miss":
            self.turn = target
        self.set_deadline(self.timings["turn"])
        self.bump()

    # -- actions --------------------------------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        kind = action.get("a")
        side = self.side_of[pid]
        if kind in ("shuffle", "move", "ready"):
            if self.phase != "place":
                raise GameError("wrong_phase", "The fleets are already at sea")
            if self.ready[side]:
                raise GameError("locked", "Your fleet is locked in")
            if kind == "shuffle":
                self.fleets[side] = place(self.rng)
                self.bump()
            elif kind == "move":
                self._move(side, action)
            else:
                self.ready[side] = True
                self.bump()
                if all(self.ready):
                    self._battle()
        elif kind == "fire":
            if self.phase != "battle":
                raise GameError("wrong_phase", "Hold your fire")
            if pid != self._shooter():
                raise GameError("not_your_turn", "It isn't your shot")
            cell = as_int(action.get("cell"), lo=0, hi=SIZE * SIZE - 1, field="Square")
            if cell in self.shots[1 - self.turn]:
                raise GameError("already_shot", "You've already fired there")
            self._fire(pid, cell)
        else:
            raise GameError("bad_action", "Unknown action")

    def _move(self, side: int, action: dict[str, Any]) -> None:
        """Put one of your ships somewhere else: `ship` (index), `cell` (its top-left square), `across`."""
        i = as_int(action.get("ship"), lo=0, hi=len(FLEET) - 1, field="Ship")
        start = as_int(action.get("cell"), lo=0, hi=SIZE * SIZE - 1, field="Square")
        across = action.get("across")
        if not isinstance(across, bool):
            raise GameError("bad_input", "Across or down?")
        cells = ship_cells(start, FLEET[i], across)
        if cells is None:
            raise GameError("off_grid", "That ship won't fit there")
        others = {c for j, ship in enumerate(self.fleets[side]) if j != i for c in ship}
        if others & set(cells):
            raise GameError("overlap", "Ships can't overlap")
        self.fleets[side][i] = cells
        self.bump()

    def _auto(self) -> None:
        """Out of time: a random square nobody has tried."""
        target = 1 - self.turn
        free = [c for c in range(SIZE * SIZE) if c not in self.shots[target]]
        self._fire(self._shooter(), self.rng.choice(free))

    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def skip(self) -> bool:
        """Only the placing: in battle a skip would fire a random shot for someone else (the turn clock
        does that when they really are away)."""
        if self.phase != "place":
            return False
        self.advance()
        return True

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "place":
            self._battle()
        else:
            self._auto()

    # -- chat -----------------------------------------------------------------------------------------
    def chat_team(self, pid: str) -> tuple[str, str] | None:
        side = self.side_of.get(pid)
        if side is None or len(self.sides[side]) < 2:
            return None
        return (f"fleet:{side}", SIDE_NAMES[side])

    # -- views ----------------------------------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        mine = self.side_of.get(pid)
        over = self.phase == "final"
        boards = []
        for side in (0, 1):
            sunk = self._sunk(side)
            boards.append(
                {
                    "shots": {str(c): r for c, r in self.shots[side].items()},
                    "sunk": sunk,
                    # where the ships are: only for their own side, or for everyone once it's over
                    "ships": self.fleets[side] if over or side == mine else None,
                    "afloat": len(FLEET) - len(sunk),
                    "ready": self.ready[side],
                }
            )
        view: dict[str, Any] = {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.shot_no,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "size": SIZE,
            "fleet": list(FLEET),
            "sides": [list(s) for s in self.sides],
            "side_names": list(SIDE_NAMES),
            "boards": boards,
            "turn": self.turn if self.phase == "battle" else None,
            "shooter": self._shooter() if self.phase == "battle" else None,
            "last": self.last,
            "winner": self.winner,
            "you": {"side": mine} if mine is not None else None,
        }
        if over:
            view["scores"] = self.scores()
            view["tally"] = self.tally
        return view

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished or self.winner is None:
            return []
        names = " & ".join(self.name_of(p) for p in self.sides[self.winner])
        out = [{"icon": "⚓", "title": "Rule the waves", "text": f"{names} sank the whole fleet"}]
        best = max(self.tally.items(), key=lambda kv: (kv[1]["sunk"], kv[1]["hits"]))
        if best[1]["sunk"] >= 2:
            out.append(
                {
                    "icon": "🎯",
                    "title": "Ship breaker",
                    "text": f"{self.name_of(best[0])} sank {best[1]['sunk']} ships",
                }
            )
        wet = max(self.tally.items(), key=lambda kv: kv[1]["shots"] - kv[1]["hits"])
        misses = wet[1]["shots"] - wet[1]["hits"]
        if misses >= 8:
            out.append(
                {
                    "icon": "💦",
                    "title": "Fish scarer",
                    "text": f"{self.name_of(wet[0])} missed {misses} times",
                }
            )
        return out

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "shots": self.shot_no}
