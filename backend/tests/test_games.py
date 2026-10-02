"""Pure-Python game engine tests (no FastAPI needed): `python -m unittest` or pytest."""

from __future__ import annotations

import random
import unittest

from app.games import REGISTRY, GameError, Player
from app.games.alibi import ASKS_PER_ROUND, INTERROGATION_ROUNDS, SLOT_LABELS, Alibi
from app.games.frenemy import FrenemyRadar
from app.games.price import ITEMS, PriceIsWeird, commitment


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def make(cls, n, seed=1):
    clock = Clock()
    players = [Player(id=f"p{i}", name=f"Name{i}") for i in range(n)]
    game = cls(players, rng=random.Random(seed), clock=clock)
    game.start()
    return game, clock, players


class RegistryTests(unittest.TestCase):
    def test_registry_has_all_games(self):
        self.assertEqual(set(REGISTRY), {"frenemy", "alibi", "price"})

    def test_player_count_enforced(self):
        with self.assertRaises(GameError):
            Alibi([Player("a", "A"), Player("b", "B")])


class FrenemyTests(unittest.TestCase):
    def test_full_game_and_blind_spot(self):
        game, clock, players = make(FrenemyRadar, 4)
        ids = [p.id for p in players]
        for _rnd in range(FrenemyRadar.ROUNDS):
            self.assertEqual(game.phase, "rank")
            for pid in ids:
                # Everyone ranks p0 first, p1 second...; p0 ranks themselves last.
                order = list(ids)
                if pid == "p0":
                    order = ids[1:] + ["p0"]
                game.handle(pid, {"a": "rank", "order": order})
            self.assertEqual(game.phase, "reveal")
            row = game.view_for("p0")["result"]["p0"]
            self.assertEqual(row["self_rank"], 4.0)
            self.assertEqual(row["others_avg"], 1.0)
            self.assertGreater(row["blind_pct"], 90)
            game.advance()
        self.assertEqual(game.phase, "final")
        self.assertTrue(game.finished)
        final = game.view_for("p1")["final"]
        self.assertEqual(max(final["per_player"], key=lambda k: final["per_player"][k]["blind_spot"]), "p0")
        award_names = {a["award"] for a in final["awards"]}
        self.assertIn("Unknown to Self", award_names)

    def test_absent_player_gets_no_award(self):
        game, _, players = make(FrenemyRadar, 4)
        ids = [p.id for p in players]
        for _rnd in range(FrenemyRadar.ROUNDS):
            for pid in ids[:3]:  # p3 never ranks
                game.handle(pid, {"a": "rank", "order": list(ids)})
            game.advance()
            game.advance()
        final = game.view_for("p0")["final"]
        self.assertNotIn("p3", {a["player"] for a in final["awards"]})
        self.assertNotIn("p3", final["per_player"])
        self.assertEqual(game.scores()["p3"], 0)  # sitting out earns nothing

    def test_rankings_are_secret_until_reveal(self):
        game, _, players = make(FrenemyRadar, 3)
        game.handle("p0", {"a": "rank", "order": ["p2", "p1", "p0"]})
        view = game.view_for("p1")
        self.assertEqual(view["submitted"], ["p0"])
        self.assertNotIn("result", view)
        self.assertNotIn("p2", str(view.get("rankings", "")))

    def test_rejects_bad_rankings(self):
        game, _, _ = make(FrenemyRadar, 3)
        for bad in (["p0", "p1"], ["p0", "p0", "p1"], ["p0", "p1", "zzz"], "p0p1p2", None, [1, 2, 3]):
            with self.assertRaises(GameError):
                game.handle("p0", {"a": "rank", "order": bad})
        with self.assertRaises(GameError):
            game.handle("ghost", {"a": "rank", "order": ["p0", "p1", "p2"]})

    def test_timer_moves_game_forward(self):
        game, clock, _ = make(FrenemyRadar, 3)
        clock.advance(61)
        game.tick()
        self.assertEqual(game.phase, "reveal")
        clock.advance(21)
        game.tick()
        self.assertEqual(game.phase, "rank")
        self.assertEqual(game.round, 1)


class PriceTests(unittest.TestCase):
    def test_commit_matches_reveal_and_hidden_before(self):
        game, _, _ = make(PriceIsWeird, 3)
        view = game.view_for("p0")
        self.assertNotIn("result", view)
        self.assertNotIn("modifier", str(view))
        self.assertNotIn("nonce", str(view))
        commit = view["commit"]
        for pid in ("p0", "p1", "p2"):
            game.handle(pid, {"a": "guess", "amount": 100})
        result = game.view_for("p0")["result"]
        self.assertEqual(commitment(result["modifier"], result["nonce"]), commit)

    def test_closest_without_going_over_wins(self):
        game, _, _ = make(PriceIsWeird, 3)
        price = int(round(game.items[0]["price"] * game.modifier))
        game.handle("p0", {"a": "guess", "amount": price + 1})  # over
        game.handle("p1", {"a": "guess", "amount": max(1, price - 5)})
        game.handle("p2", {"a": "guess", "amount": max(1, price // 2)})
        result = game.view_for("p0")["result"]
        self.assertEqual(result["winner"], "p1" if price > 5 else None)
        self.assertEqual(game.scores()["p0"], 0)

    def test_everyone_over_rolls_pot_over(self):
        game, clock, _ = make(PriceIsWeird, 2)
        price = int(round(game.items[0]["price"] * game.modifier))
        game.handle("p0", {"a": "guess", "amount": price + 10})
        game.handle("p1", {"a": "guess", "amount": price + 20})
        self.assertIsNone(game.view_for("p0")["result"]["winner"])
        self.assertEqual(game.rollover, 100)
        game.advance()  # -> next round
        self.assertEqual(game.view_for("p0")["rollover"], 100)

    def test_hedge_chip_counts_and_runs_out(self):
        game, _, _ = make(PriceIsWeird, 2)
        game.handle("p0", {"a": "guess", "amount": 5, "amount2": 6})
        self.assertEqual(game.chips["p0"], 1)
        game.handle("p1", {"a": "guess", "amount": 5})
        game.advance()
        game.handle("p0", {"a": "guess", "amount": 5, "amount2": 6})
        game.handle("p1", {"a": "guess", "amount": 5})
        game.advance()
        with self.assertRaises(GameError):
            game.handle("p0", {"a": "guess", "amount": 5, "amount2": 6})

    def test_input_validation(self):
        game, _, _ = make(PriceIsWeird, 2)
        for bad in (0, -5, 10**9, 1.5, "12", True, None):
            with self.assertRaises(GameError):
                game.handle("p0", {"a": "guess", "amount": bad})
        game.handle("p0", {"a": "guess", "amount": 5})
        with self.assertRaises(GameError):
            game.handle("p0", {"a": "guess", "amount": 6})

    def test_full_game_finishes(self):
        game, _, _ = make(PriceIsWeird, 2)
        for _ in range(PriceIsWeird.ROUNDS):
            game.advance()  # resolve guess phase
            game.advance()  # leave reveal
        self.assertTrue(game.finished)
        self.assertEqual(len(game.view_for("p0")["history"]), PriceIsWeird.ROUNDS)

    def test_item_pool_is_valid(self):
        self.assertGreaterEqual(len(ITEMS), PriceIsWeird.ROUNDS)
        for it in ITEMS:
            self.assertGreater(it["price"], 0)
            self.assertEqual(it["price"] % 2, 0)


class AlibiTests(unittest.TestCase):
    def setUp(self):
        self.game, self.clock, self.players = make(Alibi, 5, seed=7)
        self.ids = [p.id for p in self.players]

    def test_only_killer_sees_role_and_fake_slots(self):
        for pid in self.ids:
            you = self.game.view_for(pid)["you"]
            if pid == self.game.killer:
                self.assertTrue(you["is_killer"])
                self.assertEqual(len(you["fake_slots"]), 2)
            else:
                self.assertFalse(you["is_killer"])
                self.assertIsNone(you["fake_slots"])

    def test_killer_identity_never_in_other_views_before_final(self):
        killer = self.game.killer
        for pid in self.ids:
            if pid == killer:
                continue
            text = str(self.game.view_for(pid))
            self.assertNotIn("is_killer': True", text)
            self.assertNotIn("truth", self.game.view_for(pid))
            self.assertNotIn("fake_slots': [", text)

    def test_truth_generation_invariants_over_many_seeds(self):
        for seed in range(200):
            n = 4 + seed % 5
            game, _, players = make(Alibi, n, seed=seed)
            m = game.murder_slot
            killer = game.killer
            innocents = [p.id for p in players if p.id != killer]
            # Killer is alone at the scene when it happens.
            for i in innocents:
                self.assertNotEqual(game.truth[i][m], game.scene)
            # Killer's murder-slot claim is a lie about an empty room.
            claim = game.cards[killer][m]
            self.assertNotEqual(claim["location"], game.scene)
            self.assertEqual(claim["with"], [])
            for pid in game.player_ids:
                self.assertNotEqual(game.truth[pid][m], claim["location"])
            # Witness slot: killer lies, at least one innocent knows the truth.
            w = game.witness_slot
            self.assertNotEqual(m, w)
            truth_companions = [i for i in innocents if game.truth[i][w] == game.truth[killer][w]]
            self.assertTrue(truth_companions)
            for pid in game.player_ids:
                self.assertNotEqual(game.truth[pid][w], game.cards[killer][w]["location"])
            # Innocents never lie.
            for i in innocents:
                for s in range(len(SLOT_LABELS)):
                    self.assertEqual(game.cards[i][s]["location"], game.truth[i][s])

    def _to_interrogation(self):
        self.game.advance()
        self.assertEqual(self.game.phase, "interrogate")

    def test_murder_alibis_published_at_start_of_round_one(self):
        self.assertEqual(self.game.view_for("p0")["claims"], [])
        self._to_interrogation()
        claims = self.game.view_for("p0")["claims"]
        self.assertEqual(len(claims), 5)
        self.assertTrue(all(c["slot"] == self.game.murder_slot for c in claims))

    def test_ask_forces_reveal_and_is_limited(self):
        self._to_interrogation()
        asker = "p0"
        target = "p1"
        free = [s for s in range(len(SLOT_LABELS)) if s != self.game.murder_slot]
        self.game.handle(asker, {"a": "ask", "target": target, "slot": free[0]})
        self.assertIn((target, free[0]), self.game.claims)
        self.game.handle(asker, {"a": "ask", "target": target, "slot": free[1]})
        self.assertEqual(self.game.view_for(asker)["you"]["asks_left"], ASKS_PER_ROUND - 2)
        with self.assertRaises(GameError):
            self.game.handle(asker, {"a": "ask", "target": target, "slot": free[2]})
        with self.assertRaises(GameError):
            self.game.handle("p2", {"a": "ask", "target": "p2", "slot": 0})

    def test_flags_catch_the_killers_witness_slot_lie(self):
        self._to_interrogation()
        g = self.game
        w, killer = g.witness_slot, g.killer
        witness = next(i for i in g.player_ids if i != killer and g.truth[i][w] == g.truth[killer][w])
        g.handle(killer, {"a": "reveal", "slot": w})
        g.handle(witness, {"a": "reveal", "slot": w})
        flags = [f for f in g.view_for(witness)["flags"] if f["kind"] == "mismatch"]
        self.assertTrue(any(killer in f["players"] for f in flags))

    def test_camera_flag_exposes_empty_room_claim(self):
        g = self.game
        g.advance()  # round 1
        g.advance()  # round 2
        g.advance()  # round 3 -> second camera clue
        killer = g.killer
        fake_loc = g.cards[killer][g.murder_slot]["location"]
        # Force the random clue to be the empty room for a deterministic assertion.
        g.clues[-1] = g._camera(fake_loc, g.murder_slot)
        flags = [f for f in g.flags() if f["kind"] == "camera"]
        self.assertTrue(any(killer in f["players"] for f in flags))
        # Innocents' murder claims never trip a camera flag.
        self.assertTrue(all(f["players"] == [killer] for f in flags))

    def test_voting_catches_or_frees_killer(self):
        g = self.game
        for _ in range(1 + INTERROGATION_ROUNDS):
            g.advance()
        self.assertEqual(g.phase, "vote")
        for pid in self.ids:
            target = g.killer if pid != g.killer else next(i for i in self.ids if i != g.killer)
            g.handle(pid, {"a": "vote", "target": target})
        self.assertTrue(g.finished)
        res = g.view_for("p0")["result"]
        self.assertTrue(res["caught"])
        self.assertEqual(res["killer"], g.killer)
        self.assertGreater(g.scores()[next(i for i in self.ids if i != g.killer)], 0)

    def _vote_all(self, votes):
        g = self.game
        for _ in range(1 + INTERROGATION_ROUNDS):
            g.advance()
        for pid, target in votes.items():
            g.handle(pid, {"a": "vote", "target": target})
        self.assertTrue(g.finished)
        return g.view_for("p0")["result"]

    def test_killer_escapes_when_an_innocent_is_top_voted(self):
        killer = self.game.killer
        o = [i for i in self.ids if i != killer]
        votes = {o[0]: killer, o[1]: o[2], o[2]: o[3], o[3]: o[2], killer: o[2]}
        result = self._vote_all(votes)
        self.assertFalse(result["caught"])
        self.assertEqual(self.game.scores()[killer], 300)

    def test_tie_means_killer_escapes(self):
        killer = self.game.killer
        o = [i for i in self.ids if i != killer]
        # killer 2 votes, o[2] 2 votes -> tie -> killer is not the single top.
        votes = {o[0]: killer, o[1]: killer, o[2]: o[3], o[3]: o[2], killer: o[2]}
        result = self._vote_all(votes)
        self.assertFalse(result["caught"])

    def test_cannot_act_in_wrong_phase_or_vote_self(self):
        with self.assertRaises(GameError):
            self.game.handle("p0", {"a": "ask", "target": "p1", "slot": 0})  # still briefing
        for _ in range(1 + INTERROGATION_ROUNDS):
            self.game.advance()
        with self.assertRaises(GameError):
            self.game.handle("p0", {"a": "vote", "target": "p0"})
        with self.assertRaises(GameError):
            self.game.handle("p0", {"a": "vote", "target": {"x": 1}})
        with self.assertRaises(GameError):
            self.game.handle("p0", {"a": "reveal", "slot": 0})

    def test_slot_input_validation(self):
        self._to_interrogation()
        for bad in (-1, 99, "1", 1.0, None, True):
            with self.assertRaises(GameError):
                self.game.handle("p0", {"a": "reveal", "slot": bad})


if __name__ == "__main__":
    unittest.main()


class SpectatorTests(unittest.TestCase):
    """TV mode shows view_for(<non-player id>): it must carry no one's private state."""

    TV = "tv:screen"

    def test_frenemy_spectator_never_sees_rankings_before_reveal(self):
        game, _, players = make(FrenemyRadar, 4)
        ids = [p.id for p in players]
        for pid in ids[:3]:
            game.handle(pid, {"a": "rank", "order": list(reversed(ids))})
        view = game.view_for(self.TV)
        self.assertNotIn("result", view)
        self.assertFalse(view["you_submitted"])
        self.assertEqual(sorted(view["submitted"]), sorted(ids[:3]))  # who, never what

    def test_price_spectator_sees_no_guesses_or_modifier_before_reveal(self):
        game, _, players = make(PriceIsWeird, 3)
        game.handle("p0", {"a": "guess", "amount": 4321, "amount2": 8765})
        view = game.view_for(self.TV)
        dump = str(view)
        for secret in ("4321", "8765", "true_price", "modifier", "nonce", "base_price"):
            self.assertNotIn(secret, dump)
        self.assertNotIn("your_guesses", view)
        self.assertEqual(view["chips"], 0)

    def test_alibi_spectator_gets_no_card_and_no_killer(self):
        for seed in range(20):
            game, clock, players = make(Alibi, 5, seed=seed)
            game.advance()  # into interrogation
            view = game.view_for(self.TV)
            self.assertEqual(view["you"]["card"], [])
            self.assertFalse(view["you"]["is_killer"])
            self.assertIsNone(view["you"]["fake_slots"])
            self.assertNotIn("result", view)
