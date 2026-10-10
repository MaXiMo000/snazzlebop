"""The jump-scare prank: forgiving name matching, when scares are queued, who can see them, the switch."""

from __future__ import annotations

import unittest

from app import prank
from app.config import load_settings
from app.rooms import Room
from tests.test_rooms import FakeConn, HubHarness
from tests.test_show import finish

LIST = ("Max", "Zoey", "Nina", "Theo", "Kai", "Iris", "Omar")


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.want = prank.targets(LIST)

    def test_variants_match(self):
        for name in (
            "Max", "max", "MAX", "Maxxx", "Max B", "M4x", "Mex", "Zoey", "zoey", "Z0ey", "Zoeyy", "Zoei", "ZOEY🔥",
            "nina", "N1na", "Ninna", "Nyna", "7heo", "Th3o", "Thea", "Kaii", "K4i", "1ris", "ÍRIS", "omar_99",
        ):  # fmt: skip
            self.assertTrue(prank.matches(name, self.want), name)

    def test_others_dont(self):
        for name in (
            "Bo",
            "Cy",
            "Maximo",
            "Sam",
            "Theodore",
            "Bob Rider",
            "Teddy",
            "Elephant",
            "Di",
            "Zed",
        ):
            self.assertFalse(prank.matches(name, self.want), name)

    def test_empty_list_matches_nobody(self):
        self.assertFalse(prank.matches("Max", ()))
        self.assertEqual(prank.targets(()), ())

    def test_settings_switch(self):
        s = load_settings({"JUMPSCARE": "on", "JUMPSCARE_NAMES": "Max, Kai ,"})
        self.assertEqual((s.jumpscare, s.jumpscare_names), (True, ("Max", "Kai")))
        on = load_settings({})  # on by default, but no names ship with the code: nobody is pranked
        self.assertTrue(on.jumpscare)
        self.assertEqual(on.jumpscare_names, ())
        for off in ("false", "off", "0", "no", "FALSE"):
            self.assertFalse(load_settings({"JUMPSCARE": off}).jumpscare, off)
        self.assertNotIn("Max", repr(s))  # never in logs or reprs


class ScareFlowTests(HubHarness):
    def hub(self, on=True):
        return self.make_hub(jumpscare=on, jumpscare_names=LIST)

    async def test_arrival_and_every_score_screen_scare_only_the_target(self):
        hub = self.hub()
        room, host, _ = hub.create_room("Host")
        conns = {host.id: FakeConn()}
        await hub.connect(room, host.id, conns[host.id])
        _, ray, _ = hub.join_room(room.code, "Z0ey")
        _, bo, _ = hub.join_room(room.code, "Bo")
        for p in (ray, bo):
            conns[p.id] = FakeConn()
            await hub.connect(room, p.id, conns[p.id])
        self.assertEqual(conns[ray.id].last["scare"], 1)  # on arrival
        self.assertEqual(conns[bo.id].last["scare"], 0)
        self.assertEqual(conns[host.id].last["scare"], 0)
        await hub.handle_message(room, host.id, conns[host.id], {"t": "start", "game": "lonely"})
        finish(hub, room)
        await hub.broadcast(room)
        self.assertEqual(conns[ray.id].last["scare"], 2)  # the scores are up
        self.assertNotIn(ray.id, str(conns[bo.id].last["scare"]))
        await hub.handle_message(room, host.id, conns[host.id], {"t": "start", "game": "lonely"})
        finish(hub, room)
        await hub.broadcast(room)
        self.assertEqual(conns[ray.id].last["scare"], 3)

    async def test_audience_members_too(self):
        hub = self.hub()
        room, host, _ = hub.create_room("Host")
        _, fan, _ = hub.join_audience(room.code, "irys")
        f = FakeConn()
        await hub.connect(room, fan.id, f)
        self.assertEqual(f.last["scare"], 1)

    async def test_off_switch(self):
        hub = self.hub(on=False)
        room, host, _ = hub.create_room("Max")
        c = FakeConn()
        await hub.connect(room, host.id, c)
        self.assertEqual(c.last["scare"], 0)
        self.assertEqual(room.scares, {})


if __name__ == "__main__":
    unittest.main()


class RoomExtrasTests(HubHarness):
    """Walk-ons (same private list as the prank), picked faces, and the host's mute-all."""

    async def test_walk_on_for_listed_names_only(self):
        hub = self.make_hub(jumpscare=True, jumpscare_names=LIST)
        room, host, conns = await self.party(hub, 2)
        self.assertIsNone(conns[host].last["entrance"])
        _, star, _ = hub.join_room(room.code, LIST[0])
        await hub.broadcast(room)
        self.assertEqual(conns[host].last["entrance"], {"id": 1, "pid": star.id, "name": LIST[0]})
        hub.join_audience(room.code, LIST[1])
        await hub.broadcast(room)
        self.assertEqual(conns[host].last["entrance"]["id"], 2)

    async def test_faces_and_hush(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 2)
        guest = next(p for p in room.players if p != host)
        await hub.handle_message(room, guest, conns[guest], {"t": "avatar", "face": 3, "tone": 7})
        self.assertEqual(conns[host].last["faces"], {guest: [3, 7]})
        for bad in (
            {"face": 99, "tone": 0},
            {"face": True, "tone": 0},
            {"face": "1", "tone": 0},
            {"face": 0},
        ):
            await hub.handle_message(room, guest, conns[guest], {"t": "avatar", **bad})
        self.assertEqual(room.faces, {guest: [3, 7]})
        await hub.handle_message(room, guest, conns[guest], {"t": "hush"})
        self.assertIn("not_host", conns[guest].errors())
        await hub.handle_message(room, host, conns[host], {"t": "hush"})
        self.assertEqual(conns[guest].last["call"]["hush"], 1)
        await hub.handle_message(room, host, conns[host], {"t": "hush"})
        self.assertIn("slow_down", conns[host].errors())
        await hub.handle_message(room, guest, conns[guest], {"t": "leave"})
        self.assertEqual(room.faces, {})

    def test_old_snapshots_get_new_fields(self):
        hub = self.make_hub()
        room, _, _ = hub.create_room("Host")
        state = room.__getstate__()
        for gone in ("faces", "entrance"):
            state.pop(gone)
        fresh = Room.__new__(Room)
        fresh.__setstate__(state)
        self.assertEqual((fresh.faces, fresh.entrance), ({}, {}))
