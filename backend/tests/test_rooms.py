"""Room hub tests with fake connections. Pure Python, no FastAPI required."""

from __future__ import annotations

import asyncio
import random
import unittest
from typing import Any

from app.config import Settings
from app.rooms import Hub, HubError, clean_name

FAST = {
    "frenemy": {"rank": 5, "reveal": 2},
    "alibi": {"briefing": 2, "round": 5, "vote": 5},
    "price": {"guess": 5, "reveal": 2},
}


class FakeConn:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.closed: int | None = None

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent.append(data)

    async def close(self, code: int = 1000) -> None:
        self.closed = code

    @property
    def last(self) -> dict[str, Any]:
        return next(m for m in reversed(self.sent) if m["t"] == "state")

    def errors(self) -> list[str]:
        return [m["code"] for m in self.sent if m["t"] == "error"]


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class NameTests(unittest.TestCase):
    def test_accepts_normal_and_emoji_names(self):
        self.assertEqual(clean_name("  Ana   Maria "), "Ana Maria")
        self.assertEqual(clean_name("Zoë"), "Zoë")
        self.assertEqual(clean_name("Sam 🎲"), "Sam 🎲")
        self.assertEqual(clean_name("O'Neil-Jr."), "O'Neil-Jr.")

    def test_rejects_bad_names(self):
        for bad in ("", "   ", "x" * 17, "<script>", "a\nb", "a​b", "‮evil", None, 5, "a;b", 'a"b', "a/b"):
            with self.assertRaises(HubError, msg=repr(bad)):
                clean_name(bad)


class HubTests(unittest.IsolatedAsyncioTestCase):
    def make_hub(self, **overrides):
        settings = Settings(secret_key="s" * 40, **overrides)
        self.finished: list[tuple[str, dict]] = []
        self.clock = Clock()
        return Hub(
            settings,
            clock=self.clock,
            rng=random.Random(3),
            on_game_finished=lambda g, s: self.finished.append((g, s)),
            timings=FAST,
        )

    async def party(self, hub, n):
        room, host, _ = hub.create_room("Host")
        conns = {host.id: FakeConn()}
        await hub.connect(room, host.id, conns[host.id])
        for i in range(n - 1):
            _, p, _ = hub.join_room(room.code, f"Guest{i}")
            conns[p.id] = FakeConn()
            await hub.connect(room, p.id, conns[p.id])
        return room, host.id, conns

    async def test_create_join_and_limits(self):
        hub = self.make_hub(max_rooms=2, max_players_per_room=3)
        room, host, _ = hub.create_room("Host")
        self.assertEqual(len(room.code), 5)
        hub.join_room(room.code.lower(), "Two")  # codes are case-insensitive
        with self.assertRaises(HubError) as e:
            hub.join_room(room.code, "two")
        self.assertEqual(e.exception.code, "name_taken")
        hub.join_room(room.code, "Three")
        with self.assertRaises(HubError) as e:
            hub.join_room(room.code, "Four")
        self.assertEqual(e.exception.code, "room_full")
        with self.assertRaises(HubError) as e:
            hub.join_room("ZZZZZ", "Anyone")
        self.assertEqual(e.exception.status, 404)
        for bad in ("", "AB", "ABCDEFGHIJ", "ab!de", "IOIOI", "'; DROP"):
            with self.assertRaises(HubError):
                hub.join_room(bad, "x")
        hub.create_room("B")
        with self.assertRaises(HubError) as e:
            hub.create_room("C")
        self.assertEqual(e.exception.status, 503)

    async def test_only_host_can_start_and_counts_enforced(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        guest = next(i for i in conns if i != host)
        await hub.handle_message(room, guest, conns[guest], {"t": "start", "game": "price"})
        self.assertIn("not_host", conns[guest].errors())
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "alibi"})
        self.assertIn("bad_player_count", conns[host].errors())
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "nope"})
        self.assertIn("bad_game", conns[host].errors())
        self.assertEqual(room.phase, "lobby")
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "price"})
        self.assertEqual(room.phase, "game")
        self.assertEqual(conns[guest].last["game"]["game"], "price")

    async def test_bad_messages_are_rejected_not_crashing(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        for junk in ([], "x", 5, None, {"t": 5}, {"t": "evil"}, {"t": "act"}, {"t": "start", "game": ["a"]}):
            await hub.handle_message(room, host, conns[host], junk)
        self.assertEqual(room.phase, "lobby")

    async def test_alibi_secrets_do_not_leak_between_players(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 5)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "alibi"})
        killer = room.game.killer
        for pid, conn in conns.items():
            game_view = conn.last["game"]
            if pid == killer:
                self.assertTrue(game_view["you"]["is_killer"])
            else:
                self.assertFalse(game_view["you"]["is_killer"])
                self.assertIsNone(game_view["you"]["fake_slots"])
                self.assertNotIn("result", game_view)
        dump = "".join(str(conns[p].last) for p in conns if p != killer)
        self.assertNotIn(f"'killer': '{killer}'", dump)

    async def test_price_modifier_stays_hidden_until_reveal(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 2)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "price"})
        other = next(i for i in conns if i != host)
        dump = str(conns[other].last)
        self.assertNotIn(room.game.nonce, dump)
        self.assertNotIn("true_price", dump)
        await hub.handle_message(room, host, conns[host], {"t": "act", "a": "guess", "amount": 10})
        await hub.handle_message(room, other, conns[other], {"t": "act", "a": "guess", "amount": 20})
        self.assertIn("true_price", str(conns[other].last))

    async def test_finish_accumulates_scores_and_records_once(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "frenemy"})
        ids = list(conns)
        for _ in range(3):
            for pid in ids:
                await hub.handle_message(room, pid, conns[pid], {"t": "act", "a": "rank", "order": ids})
            await hub.handle_message(room, host, conns[host], {"t": "skip"})
        self.assertEqual(room.phase, "results")
        self.assertEqual(len(self.finished), 1)
        self.assertEqual(self.finished[0][0], "frenemy")
        self.assertNotIn("name", str(self.finished[0][1]).lower())
        self.assertTrue(any(v > 0 for v in room.total_scores.values()))
        before = dict(room.total_scores)
        await hub.handle_message(room, host, conns[host], {"t": "skip"})
        self.assertEqual(room.total_scores, before)
        await hub.handle_message(room, host, conns[host], {"t": "lobby"})
        self.assertEqual(room.phase, "lobby")

    async def test_stale_skip_does_not_skip_the_next_phase(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        other = next(p for p in conns if p != host)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "price"})
        seen = conns[host].last["stage"]  # host is looking at the guess phase...
        await hub.handle_message(room, other, conns[other], {"t": "act", "a": "guess", "amount": 5})
        self.assertEqual(conns[host].last["stage"], seen)  # others acting doesn't move the stage
        self.clock.t += 6
        await hub.tick()  # ...which times out into the reveal before the tap arrives
        self.assertEqual(room.game.phase, "reveal")
        await hub.handle_message(room, host, conns[host], {"t": "skip", "stage": seen})
        self.assertEqual(room.game.phase, "reveal")  # stale tap ignored
        await hub.handle_message(room, host, conns[host], {"t": "skip", "stage": conns[host].last["stage"]})
        self.assertEqual(room.game.phase, "guess")
        await hub.handle_message(room, host, conns[host], {"t": "skip", "stage": 7})
        self.assertIn("bad_message", conns[host].errors())

    async def test_timer_tick_drives_game(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 2)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "price"})
        self.clock.t += 6
        await hub.tick()
        self.assertEqual(room.game.phase, "reveal")
        self.clock.t += 3
        await hub.tick()
        self.assertEqual(room.game.phase, "guess")

    async def test_host_transfers_on_disconnect_and_reconnect_replaces_connection(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        await hub.disconnect(room, host, conns[host])
        self.assertNotEqual(room.host_id, host)
        self.assertTrue(room.players[room.host_id].connected)
        # reconnect: old connection is closed, new one takes over
        first = conns[room.host_id]
        replacement = FakeConn()
        await hub.connect(room, room.host_id, replacement)
        self.assertEqual(first.closed, 1000)
        await hub.disconnect(room, room.host_id, first)  # stale socket closing must not drop the new one
        self.assertTrue(room.players[room.host_id].connected)

    async def test_cannot_join_mid_game_and_idle_rooms_expire(self):
        hub = self.make_hub(room_idle_seconds=100)
        room, host, conns = await self.party(hub, 2)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "price"})
        with self.assertRaises(HubError) as e:
            hub.join_room(room.code, "Late")
        self.assertEqual(e.exception.code, "in_progress")
        for pid, conn in conns.items():
            await hub.disconnect(room, pid, conn)
        self.clock.t += 101
        hub.cleanup()
        self.assertNotIn(room.code, hub.rooms)

    async def test_dead_connection_does_not_block_broadcast(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        victim = next(i for i in conns if i != host)

        async def boom(data):
            raise ConnectionError("gone")

        conns[victim].send_json = boom  # type: ignore[method-assign]
        await hub.broadcast(room)
        self.assertFalse(room.players[victim].connected)
        self.assertEqual(conns[victim].closed, 1011)

    async def test_tv_viewer_is_read_only_capped_and_secret_safe(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 4)
        _, tv1 = hub.issue_tv(room.code)
        vid1 = next(iter(room.viewers))
        self.assertTrue(vid1.startswith("tv:") and hub.is_member(room, vid1))
        screen = FakeConn()
        await hub.connect(room, vid1, screen)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "alibi"})
        view = screen.last
        self.assertTrue(view["tv"])
        self.assertEqual(view["game"]["you"]["card"], [])  # the TV holds no one's card
        self.assertNotIn(vid1, [p["id"] for p in view["players"]])  # not a contestant
        for msg in ({"t": "act", "a": "vote", "target": host}, {"t": "skip"}, {"t": "lobby"}, {"t": "leave"}):
            await hub.handle_message(room, vid1, screen, msg)
        self.assertEqual(screen.errors().count("read_only"), 4)
        self.assertEqual(room.phase, "game")
        # A TV never keeps a room alive on its own.
        before = room.last_active
        self.clock.t += 50
        await hub.handle_message(room, vid1, screen, {"t": "ping"})
        self.assertEqual(room.last_active, before)
        # At most two screens: a third evicts the oldest, whose token then stops working.
        hub.issue_tv(room.code)
        hub.issue_tv(room.code)
        self.assertEqual(len(room.viewers), 2)
        self.assertFalse(hub.is_member(room, vid1))
        await asyncio.sleep(0)  # the evicted screen is closed by a task
        self.assertEqual(screen.closed, 1008)
        with self.assertRaises(HubError):
            hub.issue_tv("ZZZZZ")

    async def test_stuck_reader_never_stalls_the_room(self):
        # A client that stops reading: its sends block forever once the buffers fill.
        import asyncio
        import time

        hub = self.make_hub()
        hub.send_timeout = 0.3
        room, host, conns = await self.party(hub, 3)
        stuck = next(i for i in conns if i != host)
        closes = []

        async def hang(data):
            await asyncio.Event().wait()

        async def close(code=1000):
            closes.append(code)

        conns[stuck].send_json = hang  # type: ignore[method-assign]
        conns[stuck].close = close  # type: ignore[method-assign]
        before = len(conns[host].sent)
        t0 = time.perf_counter()
        for _ in range(10):
            await hub.handle_message(room, host, conns[host], {"t": "start", "game": "price"})
            await hub.handle_message(room, host, conns[host], {"t": "lobby"})
        # A stalling broadcast waits send_timeout (0.3 s) each time: >= 6 s for 20 (5.5 s measured before
        # the fix). Without stalls it's ~0.3 s; 2 s leaves headroom for a slow, debug-mode CI loop.
        self.assertLess(time.perf_counter() - t0, 2.0)
        # Healthy players got a frame for every message (+1 when the drop itself is broadcast).
        self.assertGreaterEqual(len(conns[host].sent) - before, 20)
        await asyncio.sleep(0.5)
        self.assertFalse(room.players[stuck].connected)
        self.assertEqual(closes, [1011])  # dropped once, not once per queued frame


if __name__ == "__main__":
    unittest.main()
