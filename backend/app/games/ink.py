"""A shared drawing: an append-only log of small pen operations, for the drawing games.

The drawer's screen sends operations in small batches; the hub checks each one here, appends it to the
log and relays it to every other screen (a separate "ink" stream: full room snapshots would be far too
big to send for every pen stroke). Snapshots carry only the log's id and length, so a screen that has
fallen behind (or just reconnected) asks for the whole log and redraws it.

Coordinates are integers on an 800 x 600 canvas. Operations:
  {"op": "line", "c": colour, "w": width, "p": [x, y, x, y, ...]}  start a stroke
  {"op": "more", "p": [x, y, ...]}                                   continue the last stroke
  {"op": "undo"}                                                    take back the last stroke
  {"op": "clear"}                                                   wipe the canvas
"""

from __future__ import annotations

import secrets
from typing import Any

from .base import GameError

WIDTH, HEIGHT = 800, 600
COLOURS = 14  # palette size (the colours themselves live in the client)
SIZES = 4
MAX_POINTS_PER_OP = 120  # numbers per message (60 points): well under the socket's 2 KB cap
MAX_OPS = 4000
MAX_POINTS = 60000


class InkLog:
    def __init__(self, max_points: int = MAX_POINTS) -> None:
        self.max_points = max_points
        self.id = secrets.token_hex(4)  # a fresh canvas gets a fresh id (screens clear theirs)
        self.ops: list[dict[str, Any]] = []
        self.points = 0
        self.open = False  # a stroke is in progress ("more" may continue it)

    def add(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Validate one operation from the drawer and append it. Returns the stored operation."""
        kind = msg.get("op")
        if len(self.ops) >= MAX_OPS or self.points >= self.max_points:
            raise GameError("canvas_full", "The canvas is full: clear it to keep drawing")
        if kind == "line":
            c, w = msg.get("c"), msg.get("w")
            if not isinstance(c, int) or isinstance(c, bool) or not 0 <= c < COLOURS:
                raise GameError("bad_ink", "Unknown colour")
            if not isinstance(w, int) or isinstance(w, bool) or not 0 <= w < SIZES:
                raise GameError("bad_ink", "Unknown pen size")
            op = {"op": "line", "c": c, "w": w, "p": self._points(msg.get("p"), at_least=2)}
            self.open = True
        elif kind == "more":
            if not self.open:
                raise GameError("bad_ink", "Start a line first")
            op = {"op": "more", "p": self._points(msg.get("p"), at_least=2)}
        elif kind in ("undo", "clear"):
            op = {"op": kind}
            self.open = False
        else:
            raise GameError("bad_ink", "Unknown drawing action")
        self.points += len(op.get("p", ())) // 2
        self.ops.append(op)
        return op

    @staticmethod
    def _points(raw: Any, at_least: int) -> list[int]:
        if (
            not isinstance(raw, list)
            or not at_least <= len(raw) <= MAX_POINTS_PER_OP
            or len(raw) % 2
            or any(not isinstance(v, int) or isinstance(v, bool) for v in raw)
        ):
            raise GameError("bad_ink", "That stroke couldn't be read")
        for i, v in enumerate(raw):
            if not 0 <= v <= (WIDTH if i % 2 == 0 else HEIGHT):
                raise GameError("bad_ink", "That stroke is off the canvas")
        return list(raw)

    def view(self) -> dict[str, Any]:
        """What snapshots carry: enough to notice a gap, not the drawing itself."""
        return {"id": self.id, "count": len(self.ops)}
