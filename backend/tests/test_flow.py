"""Pacing: the "how to play" intro before every game, Ready votes on results screens, and the lobby
keeping the last show's standings."""

from __future__ import annotations

from app.games import REGISTRY
from app.games.jackpot import Jackpot
from app.rooms import INTRO_SECONDS
from tests.test_rooms import HubHarness
from tests.test_show import finish


class IntroTests(HubHarness):
    async def test_every_game_has_rules(self):
        for gid, cls in [*REGISTRY.items(), ("jackpot", Jackpot)]:
            self.assertGreaterEqual(len(cls.HOW_TO), 3, gid)
            self.assertTrue(all(isinstance(line, str) and 10 < len(line) < 200 for line in cls.HOW_TO), gid)

    async def test_intro_then_everyone_ready_starts_the_game(self):
        hub = self.make_hub(intro=True)
        room, host, conns = await self.party(hub, 3)
        guest = next(p for p in room.players if p != host)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "price"})
        self.assertEqual((room.phase, room.game), ("intro", None))
        intro = conns[guest].last["intro"]
        self.assertEqual((intro["game"], intro["needed"]), ("price", 3))
        self.assertEqual(intro["how_to"], list(REGISTRY["price"].HOW_TO))
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "price"})
        self.assertIn("in_progress", conns[host].errors())  # no second start during the intro
        for p in room.players:
            self.assertEqual(room.phase, "intro")
            await hub.handle_message(room, p, conns[p], {"t": "ready"})
        self.assertEqual((room.phase, room.game.game_id), ("game", "price"))

    async def test_host_can_start_now_and_the_timer_starts_it_anyway(self):
        hub = self.make_hub(intro=True)
        room, host, conns = await self.party(hub, 2)
        guest = next(p for p in room.players if p != host)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "lonely"})
        await hub.handle_message(room, guest, conns[guest], {"t": "skip"})
        self.assertIn("not_host", conns[guest].errors())
        await hub.handle_message(room, host, conns[host], {"t": "skip"})
        self.assertEqual(room.phase, "game")
        await hub.handle_message(room, host, conns[host], {"t": "lobby"})
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "lonely"})
        self.clock.t += INTRO_SECONDS + 1
        await hub.tick()
        self.assertEqual(room.phase, "game")

    async def test_game_clocks_only_start_after_the_intro(self):
        hub = self.make_hub(intro=True)
        room, host, conns = await self.party(hub, 2)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "lonely"})
        self.clock.t += INTRO_SECONDS - 1
        await hub.handle_message(room, host, conns[host], {"t": "skip"})
        self.assertAlmostEqual(room.game.remaining(), room.game.timings["pick"])

    async def test_a_show_runs_through_intros_and_the_jackpot(self):
        hub = self.make_hub(intro=True)
        room, host, conns = await self.party(hub, 3)
        await hub.handle_message(room, host, conns[host], {"t": "show", "games": ["price", "telepathy"]})
        self.assertEqual((room.phase, room.show.started), ("intro", 0))
        self.assertEqual(conns[host].last["intro"]["game"], "price")
        await hub.handle_message(room, host, conns[host], {"t": "skip"})
        self.assertEqual((room.game.game_id, room.show.started), ("price", 1))
        finish(hub, room)
        await hub.handle_message(room, host, conns[host], {"t": "next"})
        self.assertEqual(conns[host].last["intro"]["game"], "telepathy")
        await hub.handle_message(room, host, conns[host], {"t": "skip"})
        finish(hub, room)
        await hub.handle_message(room, host, conns[host], {"t": "next"})
        self.assertEqual(conns[host].last["intro"]["game"], "jackpot")
        await hub.handle_message(room, host, conns[host], {"t": "skip"})
        self.assertEqual(room.game.game_id, "jackpot")
        self.assertTrue(room.show.jackpot_played)

    async def test_a_game_that_cant_run_after_the_intro_returns_to_the_lobby(self):
        hub = self.make_hub(intro=True)
        room, host, conns = await self.party(hub, 3)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "boxes"})
        guest = next(p for p in room.players if p != host)
        await hub.disconnect(room, guest, conns[guest])  # down to 2: Mystery Box needs 3
        await hub.handle_message(room, host, conns[host], {"t": "skip"})
        self.assertEqual(room.phase, "lobby")


class ReadyVoteTests(HubHarness):
    async def to_reveal(self, n=3):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, n)
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "lonely"})
        for p in room.players:
            await hub.handle_message(room, p, conns[p], {"t": "act", "a": "pick", "n": 3})
        self.assertEqual(room.game.phase, "reveal")
        return hub, room, host, conns

    async def test_everyone_ready_moves_a_results_screen_on(self):
        hub, room, host, conns = await self.to_reveal()
        stage = room.game.stage
        ready = conns[host].last["ready"]
        self.assertTrue(ready["open"])
        self.assertEqual((ready["stage"], ready["needed"]), (stage, 3))
        players = list(room.players)
        for p in players[:-1]:
            await hub.handle_message(room, p, conns[p], {"t": "ready", "stage": stage})
        self.assertEqual(room.game.stage, stage)  # one holdout: nobody gets rushed
        self.assertEqual(len(conns[host].last["ready"]["votes"]), 2)
        await hub.handle_message(room, players[-1], conns[players[-1]], {"t": "ready", "stage": stage})
        self.assertEqual(room.game.phase, "pick")
        self.assertEqual(room.game.round, 1)

    async def test_stale_votes_and_action_phases_are_refused(self):
        hub, room, host, conns = await self.to_reveal()
        await hub.handle_message(room, host, conns[host], {"t": "ready", "stage": "pick:0"})
        self.assertEqual(room.ready, set())  # an old screen's vote doesn't count
        room.game.advance()  # next round: picking is not a results screen
        await hub.handle_message(room, host, conns[host], {"t": "ready", "stage": room.game.stage})
        self.assertIn("not_now", conns[host].errors())
        await hub.broadcast(room)
        self.assertFalse(conns[host].last["ready"]["open"])

    async def test_offline_players_dont_block_and_the_audience_cant_vote(self):
        hub, room, host, conns = await self.to_reveal()
        _, fan, _ = hub.join_audience(room.code, "Fan")
        from tests.test_rooms import FakeConn

        f = FakeConn()
        await hub.connect(room, fan.id, f)
        await hub.handle_message(room, fan.id, f, {"t": "ready", "stage": room.game.stage})
        self.assertIn("audience_only", f.errors())
        away = next(p for p in room.players if p != host)
        await hub.disconnect(room, away, conns[away])
        stage = room.game.stage
        for p in room.players:
            if p != away:
                await hub.handle_message(room, p, conns[p], {"t": "ready", "stage": stage})
        self.assertNotEqual(room.game.stage, stage)


class LobbyStandingsTests(HubHarness):
    async def test_the_lobby_keeps_the_last_shows_standings(self):
        hub = self.make_hub()
        room, host, conns = await self.party(hub, 3)
        await hub.handle_message(
            room, host, conns[host], {"t": "show", "games": ["price", "telepathy"], "jackpot": False}
        )
        for _ in range(2):
            finish(hub, room)
            await hub.handle_message(room, host, conns[host], {"t": "next"})
        self.assertEqual(room.phase, "finale")
        totals = dict(room.total_scores)
        await hub.handle_message(room, host, conns[host], {"t": "lobby"})
        rows = conns[host].last["last_standings"]
        self.assertEqual({r["id"]: r["total"] for r in rows}, totals)
        self.assertEqual([r["total"] for r in rows], sorted(totals.values(), reverse=True))
        await hub.handle_message(room, host, conns[host], {"t": "start", "game": "price"})
        await hub.broadcast(room)
        self.assertEqual(conns[host].last["last_standings"], [])  # gone once the next game starts
