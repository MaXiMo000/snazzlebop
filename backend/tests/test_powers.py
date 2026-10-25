"""Power-ups v2: each game's own power-ups do what they say at the right moment and refuse otherwise;
the room sees who used what, only the user sees what it showed; one per player per game; never in
ranked games or battles; a refused one is given back."""

from __future__ import annotations

import unittest

from app.games import REGISTRY, GameError
from app.games.chicken import SHIELD_SHARE, value_at
from tests.test_games import make


class EngineTests(unittest.TestCase):
    def test_trivia(self):
        game, clock, _ = make(REGISTRY["trivia"], 3)
        line = game.use_power("p0", "trivia_fifty")
        self.assertIn("50:50", line)
        before = game.deadline
        self.assertIsNone(game.use_power("p1", "trivia_time"))
        self.assertEqual(game.deadline, before + 5)
        game.handle("p2", {"a": "answer", "choice": 0})
        with self.assertRaises(GameError):
            game.use_power("p2", "trivia_fifty")  # already answered
        with self.assertRaises(GameError):
            game.use_power("p0", "dice_peek")  # another game's power-up

    def test_draw_and_guess(self):
        game, clock, _ = make(REGISTRY["drawguess"], 3)
        with self.assertRaises(GameError):
            game.use_power("p0", "drawguess_letter")  # nothing to guess yet
        game._draw("butterfly")
        guesser = next(p for p in ("p0", "p1", "p2") if p != game.drawer)
        line = game.use_power(guesser, "drawguess_letter")
        self.assertIn("Letter", line)
        shown = [c for c in game.view_for(guesser)["pattern"] if c]
        others = [p for p in ("p0", "p1", "p2") if p not in (guesser, game.drawer)]
        self.assertGreater(
            len(shown), len([c for c in game.view_for(others[0])["pattern"] if c])
        )  # just for them
        with self.assertRaises(GameError):
            game.use_power(game.drawer, "drawguess_letter")

    def test_liars_dice(self):
        game, clock, _ = make(REGISTRY["dice"], 3)
        self.assertIn(" has a ", game.use_power("p0", "dice_peek"))

    def test_chicken_shield(self):
        game, clock, _ = make(REGISTRY["chicken"], 2)
        game.use_power("p0", "chicken_shield")
        with self.assertRaises(GameError):
            game.use_power("p0", "chicken_shield")
        game._end_round()  # nobody cashed out: the bomb got both
        bang = value_at(round(game.bomb_for("p0"), 2))
        self.assertEqual(game.result["payouts"], {"p0": int(bang * SHIELD_SHARE)})
        self.assertEqual(game.result["shielded"], ["p0"])

    def test_imposter_change_vote(self):
        game, clock, _ = make(REGISTRY["imposter"], 4)
        with self.assertRaises(GameError):
            game.use_power("p0", "imposter_revote")
        game.phase = "vote"
        game.handle("p0", {"a": "vote", "target": "p1"})
        self.assertIn("vote again", game.use_power("p0", "imposter_revote"))
        game.handle("p0", {"a": "vote", "target": "p2"})
        self.assertEqual(game.votes["p0"], "p2")


# -- the room --------------------------------------------------------------------------------------
from tests.test_accounts import Wallet  # noqa: E402
from tests.test_ranked import room_of  # noqa: E402


class RoomTests(unittest.IsolatedAsyncioTestCase):
    async def room(self, wallet, guests=0):
        hub, room, pids, conns = await room_of(3, guests=guests)
        hub.spend_powerup, hub.refund_powerup = wallet.spend, wallet.refund
        await hub.handle_message(room, pids[0], conns[pids[0]], {"t": "start", "game": "trivia"})
        return hub, room, pids, conns

    async def test_used_seen_by_all_shown_to_one_once_a_game(self):
        wallet = Wallet({(1, "trivia_fifty"): 2, (2, "trivia_time"): 1})
        hub, room, pids, conns = await self.room(wallet)
        offer = {i["id"] for i in hub.view_for(room, pids[0])["powers"]["offer"]}
        self.assertEqual(offer, {"trivia_fifty", "trivia_time"})
        await hub.handle_message(room, pids[0], conns[pids[0]], {"t": "power", "item": "trivia_fifty"})
        mine, theirs = hub.view_for(room, pids[0])["powers"], hub.view_for(room, pids[1])["powers"]
        self.assertIn("50:50", mine["mine"])
        self.assertIsNone(theirs["mine"])  # what it showed is private
        self.assertEqual([n["name"] for n in theirs["news"]], ["50/50"])  # that it was used is public
        self.assertTrue(mine["used"])
        await hub.handle_message(room, pids[0], conns[pids[0]], {"t": "power", "item": "trivia_fifty"})
        self.assertIn("already_used", conns[pids[0]].errors())
        self.assertEqual(wallet.owned[(1, "trivia_fifty")], 1)  # spent once
        await hub.handle_message(room, pids[2], conns[pids[2]], {"t": "power", "item": "trivia_time"})
        self.assertIn("no_powerup", conns[pids[2]].errors())  # doesn't own one

    async def test_refused_ones_come_back_and_rooms_that_dont_allow_them(self):
        wallet = Wallet({(2, "trivia_fifty"): 1})
        hub, room, pids, conns = await self.room(wallet)
        room.game.handle(pids[1], {"a": "answer", "choice": 0})
        await hub.handle_message(room, pids[1], conns[pids[1]], {"t": "power", "item": "trivia_fifty"})
        self.assertIn("not_now", conns[pids[1]].errors())
        self.assertEqual(wallet.owned[(2, "trivia_fifty")], 1)  # given back
        room.ranked = True
        self.assertEqual(hub.view_for(room, pids[1])["powers"]["offer"], [])
        await hub.handle_message(room, pids[0], conns[pids[0]], {"t": "power", "item": "trivia_fifty"})
        self.assertIn("no_power", conns[pids[0]].errors())

    async def test_guests_cant(self):
        hub, room, pids, conns = await self.room(Wallet({}), guests=1)
        guest = pids[-1]
        self.assertEqual(hub.view_for(room, guest)["powers"]["offer"], [])
        await hub.handle_message(room, guest, conns[guest], {"t": "power", "item": "trivia_time"})
        self.assertIn("signed_out", conns[guest].errors())
