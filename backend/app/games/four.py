"""Four in a Row (Connect Four rules, our own name): drop discs, line up four.

A 7-column, 6-row upright board. Two sides take turns dropping a disc into a column; it falls to the
lowest empty spot. Four of your discs in a line (across, up or diagonal) wins the round; a full board
is a draw. One on one, or two teams: a side's players take turns making its move. Best of 1 or 3
rounds; the side that didn't start the last round starts the next.

Scoring: winning a round is worth 300 to everyone on that side, a draw 100 each.
Everything is public. A turn clock drops a disc in a random column for a side that's away; the host
can skip the round's result screen but not someone's turn.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import Game, GameError, as_int

COLS, ROWS = 7, 6
WIN_POINTS = 300
DRAW_POINTS = 100
SIDE_NAMES = ("Red", "Yellow")
LINES = ((1, 0), (0, 1), (1, 1), (1, -1))  # across, up, both diagonals (col step, row step)


def four_at(cols: list[list[int]], c: int, r: int) -> list[tuple[int, int]]:
    """The winning cells through (c, r) if that disc makes four in a line, else []."""
    side = cols[c][r]
    for dc, dr in LINES:
        cells = [(c, r)]
        for sign in (1, -1):
            x, y = c + dc * sign, r + dr * sign
            while 0 <= x < COLS and 0 <= y < len(cols[x]) and cols[x][y] == side:
                cells.append((x, y))
                x, y = x + dc * sign, y + dr * sign
        if len(cells) >= 4:
            return sorted(cells)
    return []


class FourInARow(Game):
    game_id: ClassVar[str] = "four"
    title: ClassVar[str] = "Four in a Row"
    blurb: ClassVar[str] = (
        "Drop your discs and line up four before they do: across, up or diagonal. One on one, or the "
        "whole room in two teams."
    )
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 8
    SHOW: ClassVar[bool] = False
    CLASSIC: ClassVar[bool] = True
    TEAMS: ClassVar[bool] = True
    OPTIONS: ClassVar[dict[str, list[str]]] = {"match": ["3", "1"], "turn": ["30", "15", "60"]}
    HOW_TO: ClassVar[tuple[str, ...]] = (
        "Take turns dropping a disc into a column: it falls to the lowest empty spot.",
        "Four of yours in a line (across, up or diagonal) wins the round. A full board is a draw.",
        "In teams, your side's players take turns making the move.",
        "A round win is 300 for everyone on the side, a draw 100. Best of 3 by default.",
    )
    READING: ClassVar[frozenset[str]] = frozenset(["over"])

    @classmethod
    def default_timings(cls) -> dict[str, float]:
        return {"over": 8.0}

    def start(self) -> None:
        ids = list(self.player_ids)
        self.rng.shuffle(ids)
        if self.teams:
            self.sides = [[p for p in ids if self.teams.get(p) == t] for t in (0, 1)]
        else:
            half = (len(ids) + 1) // 2
            self.sides = [ids[:half], ids[half:]]
        self.side_of = {p: s for s, members in enumerate(self.sides) for p in members}
        self.rounds = int(self.options.get("match", "3"))
        self.turn_seconds = float(self.options.get("turn", "30"))
        self.wins = [0, 0]
        self.next_up = [0, 0]  # whose go it is within each side
        self.first = self.rng.randrange(2)
        self.history: list[dict[str, Any]] = []
        self.round = 0
        self._deal()

    def _deal(self) -> None:
        self.cols: list[list[int]] = [[] for _ in range(COLS)]
        self.moves: list[dict[str, Any]] = []
        self.turn = self.first if self.round % 2 == 0 else 1 - self.first
        self.line: list[tuple[int, int]] = []
        self.winner: int | None = None
        self.phase = "play"
        self.set_deadline(self.turn_seconds)
        self.bump()

    @property
    def mover(self) -> str:
        members = self.sides[self.turn]
        return members[self.next_up[self.turn] % len(members)]

    # -- actions --------------------------------------------------------------------------------------
    def handle(self, pid: str, action: dict[str, Any]) -> None:
        self.require_player(pid)
        if action.get("a") != "drop":
            raise GameError("bad_action", "Unknown action")
        if self.phase != "play":
            raise GameError("wrong_phase", "Not now")
        if pid != self.mover:
            raise GameError("not_your_turn", "Not your turn")
        col = as_int(action.get("col"), lo=0, hi=COLS - 1, field="Column")
        if len(self.cols[col]) >= ROWS:
            raise GameError("full", "That column is full")
        self._drop(col, pid)

    POWERS: ClassVar[dict[str, dict[str, str]]] = {
        "four_undo": {"name": "Undo", "icon": "↩️", "text": "Take back your last disc before they move"},
    }

    def use_power(self, pid: str, item: str) -> str | None:
        if item != "four_undo":
            return super().use_power(pid, item)
        last = self.moves[-1] if self.moves else None
        if self.phase != "play" or last is None or last["by"] != pid or self.turn == last["side"]:
            raise GameError("not_now", "Use it right after your own move, before they reply")
        self.moves.pop()
        self.cols[last["col"]].pop()
        side = last["side"]
        self.next_up[side] -= 1
        self.turn = side
        self.line = []
        self.set_deadline(self.turn_seconds)
        self.bump()
        return "Your disc is back in your hand: drop it again."

    def _drop(self, col: int, pid: str | None) -> None:
        side = self.turn
        self.cols[col].append(side)
        row = len(self.cols[col]) - 1
        self.moves.append({"col": col, "row": row, "side": side, "by": pid})
        self.next_up[side] += 1
        self.line = four_at(self.cols, col, row)
        if self.line:
            self._end(side)
        elif all(len(c) >= ROWS for c in self.cols):
            self._end(None)
        else:
            self.turn = 1 - side
            self.set_deadline(self.turn_seconds)
            self.bump()

    def _end(self, side: int | None) -> None:
        self.winner = side
        if side is None:
            for p in self.player_ids:
                self.add_points(p, DRAW_POINTS)
        else:
            self.wins[side] += 1
            for p in self.sides[side]:
                self.add_points(p, WIN_POINTS)
        self.history.append({"winner": side, "moves": len(self.moves)})
        self.phase = "over"
        self.set_deadline(self.timings["over"])
        self.bump()

    def _decided(self) -> bool:
        need = self.rounds // 2 + 1
        return self.round + 1 >= self.rounds or max(self.wins) >= need

    # -- clocks ---------------------------------------------------------------------------------------
    def tick(self) -> None:
        if not self.finished and self.expired():
            self.advance()

    def advance(self) -> None:
        if self.finished:
            return
        if self.phase == "play":  # the side's clock ran out: a disc in a random open column
            open_cols = [c for c in range(COLS) if len(self.cols[c]) < ROWS]
            self._drop(self.rng.choice(open_cols), None)
        elif self.phase == "over":
            if self._decided():
                self.phase = "final"
                self.deadline = None
                self.finished = True
                self.bump()
            else:
                self.round += 1
                self._deal()

    def skip(self) -> bool:
        """The result screen only: a skip mid-round would drop a disc for the side that's thinking."""
        if self.phase == "play":
            return False
        self.advance()
        return True

    # -- chat: a side of two or more has its own channel -----------------------------------------------
    def chat_team(self, pid: str) -> tuple[str, str] | None:
        side = self.side_of.get(pid)
        if side is None or len(self.sides[side]) < 2:
            return None
        return (f"side:{side}", f"Team {SIDE_NAMES[side]}")

    # -- views ----------------------------------------------------------------------------------------
    def view_for(self, pid: str) -> dict[str, Any]:
        grid = [
            [self.cols[c][r] if r < len(self.cols[c]) else None for c in range(COLS)] for r in range(ROWS)
        ]
        mine = self.side_of.get(pid)
        return {
            "game": self.game_id,
            "phase": self.phase,
            "round": self.round + 1,
            "rounds": self.rounds,
            "remaining": self.remaining(),
            "players": [{"id": p.id, "name": p.name} for p in self.players],
            "sides": [list(s) for s in self.sides],
            "grid": grid,  # grid[row][col], row 0 at the bottom; None, 0 (Red) or 1 (Yellow)
            "turn": self.turn,
            "mover": self.mover if self.phase == "play" else None,
            "last": self.moves[-1] if self.moves else None,
            "line": [list(cell) for cell in self.line],
            "winner": self.winner if self.phase != "play" else None,
            "wins": list(self.wins),
            "scores": self.scores(),
            "you": {"side": mine, "turn": self.phase == "play" and pid == self.mover}
            if mine is not None
            else None,
        }

    def highlights(self) -> list[dict[str, str]]:
        if not self.finished:
            return []
        quick = min(
            (h for h in self.history if h["winner"] is not None), key=lambda h: h["moves"], default=None
        )
        if quick is None:
            return [{"icon": "🤝", "title": "Stalemate", "text": "Not one four in a row all game"}]
        side = quick["winner"]
        names = " & ".join(self.name_of(p) for p in self.sides[side])
        return [
            {
                "icon": "🔴" if side == 0 else "🟡",
                "title": "Four!",
                "text": f"{names} won a round in {quick['moves']} discs",
            }
        ]

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "rounds": len(self.history)}
