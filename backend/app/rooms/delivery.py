"""Getting frames to screens: per-connection outboxes, ink strokes, broadcasts."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from .models import (
    INK_BACKLOG,
    Connection,
    HubError,
    Room,
    log,
)


class DeliveryMixin:
    # -- outbound: one mailbox per connection, latest state wins ---------------------------------
    # Every frame is a full snapshot, so a connection only ever needs the newest one. If a send is
    # already in flight (slow or non-reading client), the next state just replaces the pending one
    # and the broadcaster moves on: a stuck socket can never stall the players who are acting.
    # Pen strokes (drawing games) are the exception: they queue in order and go out before the next
    # snapshot, batched into one frame per canvas. A screen too far behind is told to redraw instead.
    def _box(
        self, room: Room, pid: str, conn: Connection
    ) -> tuple[dict[str, Any], asyncio.Task[None] | None]:
        box = self._mail.get(conn)
        if box is not None:
            return box, None
        box = self._mail[conn] = {"pending": None, "ink": []}
        task = asyncio.get_running_loop().create_task(self._drain(room, pid, conn))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return box, task

    def _post(
        self, room: Room, pid: str, conn: Connection, data: dict[str, Any]
    ) -> asyncio.Task[None] | None:
        box, task = self._box(room, pid, conn)
        box["pending"] = data
        return task

    def _post_ink(self, room: Room, pid: str, conn: Connection, items: list[dict[str, Any]]) -> None:
        box, _ = self._box(room, pid, conn)
        box["ink"].extend(items)
        if len(box["ink"]) > INK_BACKLOG:
            box["ink"] = [{"resync": True}]

    @staticmethod
    def _ink_frames(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Consecutive strokes on one canvas share a frame: {"t": "ink", "id", "n": first, "ops"}. A whole
        drawing sent on request is marked "full" (an empty one has no ops)."""
        frames: list[dict[str, Any]] = []
        for it in items:
            last = frames[-1] if frames else None
            if "resync" in it:
                frames.append({"t": "ink", "resync": True})
            elif (
                last
                and last.get("id") == it["id"]
                and last["n"] + len(last["ops"]) == it["n"]
                and it.get("full") == last.get("full")
            ):
                last["ops"].append(it["op"])
            else:
                frame = {
                    "t": "ink",
                    "id": it["id"],
                    "n": it["n"],
                    "ops": [] if it.get("empty") else [it["op"]],
                }
                if it.get("full") or it.get("empty"):
                    frame["full"] = True
                frames.append(frame)
        return frames

    async def _drain(self, room: Room, pid: str, conn: Connection) -> None:
        box = self._mail[conn]
        try:
            while box["pending"] is not None or box["ink"]:
                if box["ink"]:
                    items, box["ink"] = box["ink"], []
                    for frame in self._ink_frames(items):
                        await asyncio.wait_for(conn.send_json(frame), timeout=self.send_timeout)
                    continue
                data, box["pending"] = box["pending"], None
                await asyncio.wait_for(conn.send_json(data), timeout=self.send_timeout)
        except Exception:
            # Slow or dead client: drop it (once) rather than queue frames for it.
            self._mail.pop(conn, None)
            log.info("dropping unresponsive connection")
            with contextlib.suppress(Exception):
                await conn.close(1011)
            await self.disconnect(room, pid, conn)
            return
        self._mail.pop(conn, None)

    async def broadcast(self, room: Room) -> None:
        self._persist(room)  # every change is broadcast, so every change is saved
        tasks = [
            task
            for pid, conn in self._targets(room)
            if (task := self._post(room, pid, conn, self.view_for(room, pid))) is not None
        ]
        if tasks:
            # Healthy sockets finish almost at once; anything slower keeps going in the background.
            await asyncio.wait(tasks, timeout=0.25)
        else:
            # Every recipient already has a send in flight: yield so those drains can run even if
            # our caller never awaits anything else.
            await asyncio.sleep(0)

    async def send_error(self, conn: Connection, code: str, message: str) -> None:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(conn.send_json({"t": "error", "code": code, "message": message}), 5)

    # Drawing games expose: ink(pid, msg) -> the canvas the stroke went on; canvas_for(pid) -> the live
    # canvas a screen shows (strokes are relayed only to screens showing that canvas, so a secret drawing
    # stays secret); and optionally drawing(pid, id) -> a finished drawing that screen may look at.
    async def _ink(self, room: Room, pid: str, conn: Connection, msg: dict[str, Any]) -> None:
        """A pen stroke from the artist: checked by the game, then relayed to the screens watching it."""
        async with room.lock:
            game = room.game
            draw = getattr(game, "ink", None)
            if room.phase != "game" or game is None or draw is None:
                raise HubError("no_canvas", "Nothing to draw on")
            canvas = draw(pid, msg)
            item = {"id": canvas.id, "n": len(canvas.ops) - 1, "op": canvas.ops[-1]}
            for to, c in self._targets(room):
                if c is not conn and game.canvas_for(to) is canvas:  # type: ignore[attr-defined]
                    self._post_ink(room, to, c, [item])
        self._persist(room)
        await asyncio.sleep(0)

    def _ink_sync(self, room: Room, pid: str, conn: Connection, msg: dict[str, Any]) -> None:
        """A screen that missed strokes (or just arrived) gets the whole drawing again; with an id, a
        finished drawing it is allowed to see (e.g. a page of the Draw Telephone album)."""
        game = room.game if room.phase == "game" else None
        if game is None or not hasattr(game, "canvas_for"):
            return
        want = msg.get("id")
        if want is None:
            canvas = game.canvas_for(pid)
        elif isinstance(want, str) and len(want) <= 16 and hasattr(game, "drawing"):
            canvas = game.drawing(pid, want)
        else:
            return
        if canvas is None:
            return
        box, _ = self._box(room, pid, conn)
        full = [{"id": canvas.id, "n": i, "op": op, "full": True} for i, op in enumerate(canvas.ops)]
        if not full:
            full = [{"id": canvas.id, "n": 0, "empty": True}]
        box["ink"] = [it for it in box["ink"] if it.get("id") != canvas.id] + full

    @staticmethod
    def _targets(room: Room) -> list[tuple[str, Connection]]:
        return [
            *room.conns.items(),
            *((v, c) for v, c in room.viewers.items() if c is not None),
            *((w.id, w.conn) for w in room.audience.values() if w.conn is not None),
        ]
