"""Chat: everyone's channel, private team channels, games that silence players, validation, rate limits,
who may post (not the TV), and that team talk never reaches the other team."""

from __future__ import annotations

import pickle

from app.rooms import CHAT_MAX, HubError, clean_chat

from .test_rooms import FakeConn, HubHarness


def texts(conn: FakeConn) -> list[str]:
    return [m["text"] for m in conn.last["chat"]["messages"]]


class CleanTests(HubHarness):
    async def test_text(self):
        self.assertEqual(clean_chat("  hello   there "), "hello there")
        self.assertEqual(
            clean_chat("family \U0001f468‍\U0001f469‍\U0001f467 time"),
            "family \U0001f468‍\U0001f469‍\U0001f467 time",
        )
        for bad in (None, 5, "", "   ", "x" * (CHAT_MAX + 1), "evil ‮ text", "zero​width", "bell\x07"):
            with self.assertRaises(HubError, msg=repr(bad)):
                clean_chat(bad)


class ChatTests(HubHarness):
    async def say(self, room, pid, conn, text, to="all"):
        self.clock.t += 2  # past the per-person gap
        await self.hub.handle_message(room, pid, conn, {"t": "chat", "text": text, "to": to})

    async def test_everyone_channel_and_who_may_post(self):
        self.hub = self.make_hub()
        room, host, conns = await self.party(self.hub, 3)
        guest = next(p for p in conns if p != host)
        await self.say(room, host, conns[host], "hi all")
        for c in conns.values():
            self.assertEqual(texts(c), ["hi all"])
        msg = conns[guest].last["chat"]["messages"][0]
        self.assertEqual((msg["name"], msg["team"]), ("Host", False))
        # The TV reads but can't post; the audience can post to everyone, not to a team.
        _, _tv = self.hub.issue_tv(room.code)
        vid = next(iter(room.viewers))
        screen = FakeConn()
        await self.hub.connect(room, vid, screen)
        await self.say(room, vid, screen, "tv talking")
        self.assertIn("read_only", screen.errors())
        self.assertEqual(texts(screen), ["hi all"])
        self.assertFalse(screen.last["chat"]["can_send"])
        _, fan, _ = self.hub.join_audience(room.code, "Fan")
        fan_conn = FakeConn()
        await self.hub.connect(room, fan.id, fan_conn)
        await self.say(room, fan.id, fan_conn, "go team!")
        await self.say(room, fan.id, fan_conn, "secret", to="team")
        self.assertIn("no_team", fan_conn.errors())
        self.assertEqual(texts(conns[host]), ["hi all", "go team!"])

    async def test_rate_limits(self):
        self.hub = self.make_hub()
        room, host, conns = await self.party(self.hub, 3)
        await self.hub.handle_message(room, host, conns[host], {"t": "chat", "text": "one"})
        await self.hub.handle_message(room, host, conns[host], {"t": "chat", "text": "two"})
        self.assertIn("slow_down", conns[host].errors())
        self.assertEqual(texts(conns[host]), ["one"])
        for i in range(20):
            self.clock.t += 0.35  # three people take turns: each stays past their own gap
            pid = list(conns)[i % 3]
            await self.hub.handle_message(room, pid, conns[pid], {"t": "chat", "text": f"m{i}"})
        sent = len(room.chat)
        self.assertLess(sent, 21)  # the room-wide burst cap held some back

    async def test_team_chat_stays_in_the_team(self):
        self.hub = self.make_hub()
        room, host, conns = await self.party(self.hub, 4)
        await self.hub.handle_message(
            room, host, conns[host], {"t": "start", "game": "truthdare", "teams": True}
        )
        teams = room.game.teams
        mate = next(p for p in conns if p != host and teams[p] == teams[host])
        rivals = [p for p in conns if teams[p] != teams[host]]
        self.assertTrue(conns[host].last["chat"]["team"].startswith("Team "))
        await self.say(room, host, conns[host], "our plan", to="team")
        await self.say(room, rivals[0], conns[rivals[0]], "their plan", to="team")
        self.assertEqual(texts(conns[host]), ["our plan"])
        self.assertEqual(texts(conns[mate]), ["our plan"])
        for r in rivals:
            self.assertEqual(texts(conns[r]), ["their plan"])
        self.assertTrue(conns[mate].last["chat"]["messages"][0]["team"])
        # A new game: the old teams' private talk is gone; everyone's messages stay.
        await self.say(room, host, conns[host], "public")
        await self.hub.handle_message(room, host, conns[host], {"t": "lobby"})
        await self.hub.handle_message(room, host, conns[host], {"t": "start", "game": "price"})
        self.assertEqual([m["text"] for m in room.chat], ["public"])
        self.assertTrue(pickle.dumps(room))  # the room (with its chat) still snapshots

    async def test_games_that_restrict_chat(self):
        self.hub = self.make_hub()
        room, host, conns = await self.party(self.hub, 4)
        # Last Card partners may not talk privately (that would be sharing hands).
        await self.hub.handle_message(
            room, host, conns[host], {"t": "start", "game": "lastcard", "teams": True}
        )
        self.assertIsNone(conns[host].last["chat"]["team"])
        await self.say(room, host, conns[host], "psst", to="team")
        self.assertIn("no_team", conns[host].errors())
        # Codewords: spymasters stay silent once the game is under way; guessers have team chat.
        # (and its own red/blue teams are not the room's Teams switch: no team badge, no team scores)
        await self.hub.handle_message(room, host, conns[host], {"t": "lobby"})
        await self.hub.handle_message(room, host, conns[host], {"t": "start", "game": "codewords"})
        g = room.game
        self.assertEqual(room.teams, {})
        self.assertIsNone(self.hub.view_for(room, host)["teams"])
        g.phase = "clue"
        spy = next(iter(g.spymasters.values()))
        guesser = next(p for p in conns if p not in g.spymasters.values())
        await self.say(room, spy, conns[spy], "it's the ocean ones")
        self.assertIn("muted", conns[spy].errors())
        self.assertTrue(self.hub.view_for(room, spy)["chat"]["muted"])
        await self.say(room, guesser, conns[guesser], "thinking BAT", to="team")
        self.assertEqual(texts(conns[guesser])[-1], "thinking BAT")
        self.assertEqual(conns[guesser].last["chat"]["team"], f"{g.teams[guesser].capitalize()} team")
        # Chess: a side of one has no team chat.
        await self.hub.handle_message(room, host, conns[host], {"t": "lobby"})
        for p in list(conns)[2:]:
            await self.hub.disconnect(room, p, conns[p])
        await self.hub.handle_message(room, host, conns[host], {"t": "start", "game": "chess"})
        self.assertIsNone(conns[host].last["chat"]["team"])
