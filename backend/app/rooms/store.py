"""Room snapshots: save after every change, restore on first use."""

from __future__ import annotations

import asyncio
from typing import Any

from .. import persist
from .models import (
    ROOM_CODE_RE,
    Room,
    log,
)


class PersistMixin:
    # -- snapshots: rooms survive a restart ----------------------------------------------------------
    def _shared(self) -> dict[str, Any]:
        return {"rng": self.rng, "clock": self.clock}

    def _persist(self, room: Room) -> None:
        """Save this room soon. Saves never overlap per room; the newest state always lands last."""
        room.touched = True
        if self.store is None or not self.store.ready:
            return
        if room.code in self._saving:
            self._saving[room.code] = True
            return
        try:
            task = asyncio.get_running_loop().create_task(self._save(room))
        except RuntimeError:  # no event loop (a sync caller in tests): nothing to save with
            return
        self._saving[room.code] = False
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _save(self, room: Room) -> None:
        try:
            while True:
                self._saving[room.code] = False
                if self.rooms.get(room.code) is not room or self.store is None:
                    return
                try:
                    blob = persist.dump_room(room, self.settings.secret_key, self._shared())
                except Exception:
                    log.exception("could not snapshot a room")
                    return
                await self.store.save_snapshot(room.code, blob)
                if not self._saving.get(room.code):
                    return
        finally:
            self._saving.pop(room.code, None)

    async def flush(self) -> None:
        """Save every room now (shutdown: the next server picks them up)."""
        if self.store is None or not self.store.ready:
            return
        for room in list(self.rooms.values()):
            try:
                blob = persist.dump_room(room, self.settings.secret_key, self._shared())
            except Exception:
                log.exception("could not snapshot a room")
                continue
            await self.store.save_snapshot(room.code, blob)

    async def fetch(self, code: str) -> Room | None:
        """The room with this code: in memory, or restored from its snapshot after a restart. A copy
        restored here that nobody has touched yet is refreshed if a newer snapshot has landed (during a
        deploy the old server keeps saving until it shuts down)."""
        if not isinstance(code, str) or not ROOM_CODE_RE.match(code):
            return None
        room = self.rooms.get(code)
        if room is not None and not (room.restored and not room.touched):
            return room
        if self.store is None or not self.store.ready:
            return room
        blob = await self.store.load_snapshot(code)
        if blob is None:
            return room
        if room is not None and persist.fingerprint(blob) == room.snapshot:
            return room
        loaded = persist.load_room(blob, self.settings.secret_key, self._shared())
        if loaded is None or self.clock() - loaded.created > self.settings.room_max_age_seconds:
            return room
        if self.rooms.get(code) is not room:  # someone else restored it while we waited
            return self.rooms.get(code)
        loaded.restored, loaded.touched, loaded.snapshot = True, False, persist.fingerprint(blob)
        loaded.last_active = self.clock()
        self.rooms[code] = loaded
        log.info("room restored from its snapshot")
        return loaded
