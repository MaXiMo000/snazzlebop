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


class MoreEngineTests(unittest.TestCase):
    def test_four_in_a_row_undo(self):
        game, clock, _ = make(REGISTRY["four"], 2)
        mover = game.mover
        with self.assertRaises(GameError):
            game.use_power(mover, "four_undo")  # nothing to undo yet
        game.handle(mover, {"a": "drop", "col": 3})
        replier = game.mover
        with self.assertRaises(GameError):
            game.use_power(replier, "four_undo")  # not their disc
        game.use_power(mover, "four_undo")
        self.assertEqual((game.mover, game.cols[3], game.moves), (mover, [], []))
        game.handle(mover, {"a": "drop", "col": 2})
        game.handle(game.mover, {"a": "drop", "col": 2})
        with self.assertRaises(GameError):
            game.use_power(mover, "four_undo")  # they've replied: too late

    def test_would_you_rather_ask_the_room(self):
        game, clock, _ = make(REGISTRY["rather"], 4)
        guessers = [p for p in ("p0", "p1", "p2", "p3") if p != game.hot]
        with self.assertRaises(GameError):
            game.use_power(guessers[0], "rather_room")  # nobody has answered yet
        game.handle(guessers[1], {"a": "answer", "pick": 0, "guess": 0})
        self.assertIn("leans", game.use_power(guessers[0], "rather_room"))
        with self.assertRaises(GameError):
            game.use_power(game.hot, "rather_room")  # never for the hot seat


class ThirdEngineTests(unittest.TestCase):
    def test_battleships_sonar(self):
        game, clock, _ = make(REGISTRY["ships"], 2)
        with self.assertRaises(GameError):
            game.use_power("p0", "ships_sonar")  # still placing
        for p in ("p0", "p1"):
            game.handle(p, {"a": "ready"})
        self.assertRegex(game.use_power("p0", "ships_sonar"), r"Sonar: \d+ unfound ship square")

    def test_hangman_vowel(self):
        game, clock, _ = make(REGISTRY["hangman"], 2)
        game.handle(game.setter, {"a": "set", "word": "elephant"})
        with self.assertRaises(GameError):
            game.use_power(game.setter, "hangman_vowel")  # not their turn
        line = game.use_power(game.guesser, "hangman_vowel")
        self.assertIn(line[-3], "EA")
        self.assertEqual(game.round_scores[game.guesser], 0)  # no points for it
        game.use_power(game.guesser, "hangman_vowel")
        with self.assertRaises(GameError):
            game.use_power(game.guesser, "hangman_vowel")  # no vowels left

    def test_truth_or_dare_another_card(self):
        game, clock, _ = make(REGISTRY["truthdare"], 3)
        with self.assertRaises(GameError):
            game.use_power(game.target, "tod_fresh")  # no card yet
        game.advance()
        game.handle(game.target, {"a": "choose", "choice": "dare"})
        rerolls = dict(game.rerolls)
        self.assertIsNone(game.use_power(game.target, "tod_fresh"))
        self.assertEqual(game.rerolls, rerolls)  # the free re-roll is still there


class FourthEngineTests(unittest.TestCase):
    def test_word_race_free_letter(self):
        game, clock, _ = make(REGISTRY["wordrace"], 2)
        line = game.use_power("p0", "wordrace_letter")
        i = int(line.split()[1]) - 1
        self.assertEqual(line, f"Letter {i + 1} is {game.answer[i]}.")
        self.assertNotIn(game.answer, str(game.view_for("p1")))  # nothing new for anyone else
        game.board["p0"] = [("XXXXX", "gggg" + "x")]  # four greens: only the last letter is left
        with self.assertRaises(GameError):
            game.use_power("p0", "wordrace_letter")

    def test_code_crackers_peek(self):
        game, clock, _ = make(REGISTRY["codes"], 2)
        with self.assertRaises(GameError):
            game.use_power("p0", "codes_peek")  # codes not set yet
        for p in ("p0", "p1"):
            game.handle(p, {"a": "set", "code": [0, 1, 2, 3]})
        self.assertIn("in position", game.use_power("p0", "codes_peek"))
        self.assertEqual(game.scores()["p0"], 0)  # free, unlike a bought hint

    def test_last_card_peek(self):
        game, clock, _ = make(REGISTRY["lastcard"], 2)
        while game.phase != "play":
            game.advance()
        line = game.use_power("p0", "lastcard_peek")
        self.assertTrue(line.startswith("The next card on the pile is a "))
        game.deck = []
        with self.assertRaises(GameError):
            game.use_power("p0", "lastcard_peek")

    def test_snake_repellent(self):
        from app.games import snakes

        game, clock, _ = make(REGISTRY["snakes"], 2)
        pid = game.current
        head = next(iter(snakes.SNAKES))
        game.pos[pid] = head - 3
        game.rng.randint = lambda a, b: 3  # lands on the snake's head
        game.use_power(pid, "snakes_repel")
        with self.assertRaises(GameError):
            game.use_power(pid, "snakes_repel")  # already protected
        game._roll()
        self.assertEqual(game.pos[pid], head)
        self.assertEqual(game.last["via"], "repelled")
        self.assertEqual(game.stats[pid]["snakes"], 0)
        self.assertNotIn(pid, game.repel)  # used up

    def test_five_dice_extra_roll(self):
        game, clock, _ = make(REGISTRY["fivedice"], 2)
        while game.phase != "play":
            game.advance()
        held = [False] * 5
        game.handle("p0", {"a": "roll"})
        game.use_power("p0", "fivedice_roll")
        with self.assertRaises(GameError):
            game.use_power("p0", "fivedice_roll")
        for _ in range(3):
            game.handle("p0", {"a": "roll", "held": held})
        self.assertEqual(game.cards["p0"].rolls, 4)
        with self.assertRaises(GameError):
            game.handle("p0", {"a": "roll", "held": held})  # four is the limit


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
