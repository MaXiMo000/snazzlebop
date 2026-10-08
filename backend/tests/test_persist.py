"""Room snapshots: every game survives a restart mid-play (same views, keeps playing), tampered or
foreign snapshots are refused, rooms come back on demand, and ended rooms are deleted."""

from __future__ import annotations

import random

from app import persist
from app.config import Settings
from app.games import REGISTRY
from app.rooms import Hub
from tests.test_rooms import FAST, Clock, FakeConn, HubHarness


class MemoryStore:
    ready = True

    def __init__(self) -> None:
        self.rows: dict[str, bytes] = {}

    async def save_snapshot(self, code: str, data: bytes) -> None:
        self.rows[code] = data

    async def load_snapshot(self, code: str) -> bytes | None:
        return self.rows.get(code)

    async def delete_snapshots(self, codes: list[str]) -> None:
        for c in codes:
            self.rows.pop(c, None)


def hub_for(store: MemoryStore, clock: Clock, seed: int = 3) -> Hub:
    return Hub(
        Settings(secret_key="s" * 40),
        clock=clock,
        rng=random.Random(seed),
        timings=FAST,
        intro_seconds=0,
        store=store,
    )


async def settle(hub: Hub) -> None:
    """Let the background saves land."""
    for _ in range(5):
        if not hub._tasks:
            return
        await __import__("asyncio").gather(*list(hub._tasks))


def public(hub: Hub, room, pid: str) -> dict:
    """What this player's screen shows of the game (who's online differs: nobody's reconnected yet)."""
    view = hub.view_for(room, pid)
    return {"phase": view["room"]["phase"], "game": view["game"], "scores": room.total_scores}


class SnapshotTests(HubHarness):
    async def test_every_game_survives_a_restart_mid_play(self):
        for gid in REGISTRY:
            with self.subTest(game=gid):
                store, clock = MemoryStore(), Clock()
                hub = hub_for(store, clock)
                room, host, conns = await self.party(hub, 5)
                await hub.handle_message(room, host, conns[host], {"t": "start", "game": gid})
                self.assertEqual(room.phase, "game", conns[host].errors())
                for _ in range(2):  # get a little way in
                    clock.t += 3
                    await hub.tick()
                await hub.flush()
                before = {pid: public(hub, room, pid) for pid in room.players}

                fresh = hub_for(store, clock, seed=9)  # a new server: new process, new random source
                back = await fresh.fetch(room.code)
                self.assertIsNotNone(back)
                self.assertTrue(back.restored)
                self.assertFalse(any(p.connected for p in back.players.values()))
                for pid, view in before.items():
                    self.assertEqual(public(fresh, back, pid), view)
                # and it keeps playing on the new server
                again = {pid: FakeConn() for pid in back.players}
                for pid, c in again.items():
                    await fresh.connect(back, pid, c)
                for _ in range(4):
                    clock.t += 30
                    await fresh.tick()
                    if back.game is not None and not back.game.finished:
                        await fresh.handle_message(
                            back, host, again[host], {"t": "skip", "stage": back.game.stage}
                        )
                self.assertTrue(again[host].sent)

    async def test_a_show_night_survives_a_restart(self):
        store, clock = MemoryStore(), Clock()
        hub = hub_for(store, clock)
        room, host, conns = await self.party(hub, 4)
        show = {"t": "show", "games": ["lonely", "telepathy"], "jackpot": True, "market": True}
        await hub.handle_message(room, host, conns[host], show)
        self.assertIsNotNone(room.show, conns[host].errors())
        for _ in range(3):
            clock.t += 40
            await hub.tick()
        await hub.flush()
        fresh = hub_for(store, clock, seed=9)
        back = await fresh.fetch(room.code)
        self.assertEqual(public(fresh, back, host), public(hub, room, host))
        self.assertEqual(back.show.games, room.show.games)
        self.assertEqual(back.show.cards, room.show.cards)

    async def test_a_snapshot_must_be_this_servers(self):
        store, clock = MemoryStore(), Clock()
        hub = hub_for(store, clock)
        room, _, _ = await self.party(hub, 2)
        await hub.flush()
        blob = store.rows[room.code]
        shared = {"rng": hub.rng, "clock": hub.clock}
        self.assertIsNotNone(persist.load_room(blob, "s" * 40, shared))
        self.assertIsNone(persist.load_room(blob, "t" * 40, shared))  # another server's secret
        tampered = blob[:-5] + bytes(b ^ 1 for b in blob[-5:])
        self.assertIsNone(persist.load_room(tampered, "s" * 40, shared))
        self.assertIsNone(persist.load_room(b"not a snapshot", "s" * 40, shared))
        store.rows[room.code] = tampered
        self.assertIsNone(await hub_for(store, clock).fetch(room.code))

    async def test_rooms_come_back_on_demand_and_newer_snapshots_win_until_touched(self):
        store, clock = MemoryStore(), Clock()
        old = hub_for(store, clock)
        room, host, conns = await self.party(old, 3)
        await settle(old)
        new = hub_for(store, clock)
        self.assertNotIn(room.code, new.rooms)
        first = await new.fetch(room.code)
        self.assertEqual(set(first.players), set(room.players))
        # The old server (still up during a deploy) changes the room and saves it.
        await old.handle_message(room, host, conns[host], {"t": "title", "title": "Friday Night"})
        await settle(old)
        second = await new.fetch(room.code)
        self.assertIsNot(second, first)
        self.assertEqual(second.title, "Friday Night")
        # Once this server changes the room itself, its copy is the one that counts.
        conn = FakeConn()
        await new.connect(second, host, conn)
        await settle(new)
        self.assertIs(await new.fetch(room.code), second)
        self.assertIsNone(await new.fetch("ZZZZZ"))
        self.assertIsNone(await new.fetch("bad code"))

    async def test_ended_rooms_are_deleted(self):
        store, clock = MemoryStore(), Clock()
        hub = hub_for(store, clock)
        room, _, conns = await self.party(hub, 2)
        await settle(hub)
        self.assertIn(room.code, store.rows)
        for pid in list(conns):
            await hub.disconnect(room, pid, conns[pid])
        clock.t += hub.settings.room_idle_seconds + 1
        hub.cleanup()
        await settle(hub)
        self.assertNotIn(room.code, store.rows)
        self.assertIsNone(await hub.fetch(room.code))
