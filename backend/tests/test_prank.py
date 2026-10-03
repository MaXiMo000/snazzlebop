"""The jump-scare prank: forgiving name matching, when scares are queued, who can see them, the switch."""

from __future__ import annotations

import unittest

from app import prank
from app.config import load_settings
from tests.test_rooms import FakeConn, HubHarness
from tests.test_show import finish

LIST = ("Ray", "Eazy", "Ana", "Leo", "Teng", "Sky", "Elsa")


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.want = prank.targets(LIST)

    def test_variants_match(self):
        for name in (
            "Ray", "ray", "RAY", "Rayyy", "Ray B", "Eazy", "eazy", "Ea7y", "3azy", "Eazi", "Easy", "EAZY🔥",
            "ana", "Anna", "Leo", "le0", "Teng", "tenng", "Sky", "Skye", "Elsa", "Elza", "ÉLSA", "elsa_99",
        ):  # fmt: skip
            self.assertTrue(prank.matches(name, self.want), name)

    def test_others_dont(self):
        for name in (
            "Bo",
            "Cy",
            "Maximo",
            "Sam",
            "Raymond",
            "Bob Rider",
            "Teddy",
            "Elephant",
            "Di",
            "Zed",
        ):
            self.assertFalse(prank.matches(name, self.want), name)

    def test_empty_list_matches_nobody(self):
        self.assertFalse(prank.matches("Ray", ()))
        self.assertEqual(prank.targets(()), ())

    def test_settings_switch(self):
        s = load_settings({"JUMPSCARE": "on", "JUMPSCARE_NAMES": "Ray, Sky ,"})
        self.assertEqual((s.jumpscare, s.jumpscare_names), (True, ("Ray", "Sky")))
        on = load_settings({})  # on by default, with the built-in list
        self.assertTrue(on.jumpscare)
        self.assertIn("Eazy", on.jumpscare_names)
        for off in ("false", "off", "0", "no", "FALSE"):
            self.assertFalse(load_settings({"JUMPSCARE": off}).jumpscare, off)
        self.assertNotIn("Ray", repr(s))  # never in logs or reprs


class ScareFlowTests(HubHarness):
    def hub(self, on=True):
        return self.make_hub(jumpscare=on, jumpscare_names=LIST)

    async def test_arrival_and_every_score_screen_scare_only_the_target(self):
        hub = self.hub()
        room, host, _ = hub.create_room("Host")
        conns = {host.id: FakeConn()}
        await hub.connect(room, host.id, conns[host.id])
        _, ray, _ = hub.join_room(room.code, "Ea7y")
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
        _, fan, _ = hub.join_audience(room.code, "skye")
        f = FakeConn()
        await hub.connect(room, fan.id, f)
        self.assertEqual(f.last["scare"], 1)

    async def test_off_switch(self):
        hub = self.hub(on=False)
        room, host, _ = hub.create_room("Ray")
        c = FakeConn()
        await hub.connect(room, host.id, c)
        self.assertEqual(c.last["scare"], 0)
        self.assertEqual(room.scares, {})


if __name__ == "__main__":
    unittest.main()
