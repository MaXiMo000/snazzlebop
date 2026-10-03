"""The second wave of game features: tested rules, secrecy (players, TV and audience) and highlights."""

from __future__ import annotations

import random
import unittest

from app.games import GameError, Player
from app.games.frenemy import MIRROR_CLOSE, MIRROR_EXACT, FrenemyRadar

SPECTATORS = ("tv:screen", "au:fan")


def make(cls, n, seed=1, **kw):
    players = [Player(id=f"p{i}", name=f"N{i}") for i in range(n)]
    game = cls(players, rng=random.Random(seed), **kw)
    game.start()
    return game


class FrenemyUpgradeTests(unittest.TestCase):
    def test_mirror_bonus_for_guessing_where_the_room_ranks_you(self):
        g = make(FrenemyRadar, 4)
        # Everyone puts p0 first, p1 second, p2 third, p3 last.
        order = ["p0", "p1", "p2", "p3"]
        g.handle("p0", {"a": "rank", "order": order, "predict": 1})  # room says #1: spot on
        g.handle("p1", {"a": "rank", "order": order, "predict": 3})  # room says #2: one off
        g.handle("p2", {"a": "rank", "order": order, "predict": 1})  # room says #3: miles off
        g.handle("p3", {"a": "rank", "order": order})  # no guess, no bonus
        res = g.results[0]
        self.assertEqual([res[p]["mirror"] for p in order], [MIRROR_EXACT, MIRROR_CLOSE, 0, 0])
        self.assertEqual(g.scores()["p0"], 100 + MIRROR_EXACT)  # blind spot 0 + bonus

    def test_predictions_are_secret_until_the_reveal(self):
        g = make(FrenemyRadar, 3)
        g.handle("p0", {"a": "rank", "order": ["p0", "p1", "p2"], "predict": 2})
        self.assertEqual(g.view_for("p0")["you_predicted"], 2)
        for viewer in ("p1", "p2", *SPECTATORS):
            view = g.view_for(viewer)
            self.assertIsNone(view["you_predicted"])
            self.assertNotIn("result", view)

    def test_prediction_validation(self):
        g = make(FrenemyRadar, 3)
        for bad in (0, 4, True, "1", 1.5):
            with self.assertRaises(GameError, msg=repr(bad)):
                g.handle("p0", {"a": "rank", "order": ["p0", "p1", "p2"], "predict": bad})
        self.assertNotIn("p0", g.rankings[0])  # a bad prediction rejects the whole submission

    def test_frenemies_and_fans(self):
        g = make(FrenemyRadar, 4)
        for _ in range(3):
            # p0 and p1 adore each other; p2 and p3 always put each other last.
            g.handle("p0", {"a": "rank", "order": ["p1", "p0", "p2", "p3"]})
            g.handle("p1", {"a": "rank", "order": ["p0", "p1", "p3", "p2"]})
            g.handle("p2", {"a": "rank", "order": ["p2", "p0", "p1", "p3"]})
            g.handle("p3", {"a": "rank", "order": ["p3", "p0", "p1", "p2"]})
            g.advance()  # reveal -> next round / final
        self.assertTrue(g.finished)
        pairs = g.final["pairs"]
        self.assertEqual(sorted(pairs["frenemies"]), ["p2", "p3"])
        self.assertEqual(sorted(pairs["fans"]), ["p0", "p1"])
        titles = [h["title"] for h in g.highlights()]
        self.assertIn("Total frenemies", titles)
        self.assertIn("Mutual fans", titles)

    def test_no_pairs_when_nobody_ranked(self):
        g = make(FrenemyRadar, 3)
        for _ in range(6):
            g.advance()
        self.assertTrue(g.finished)
        self.assertEqual(g.final["pairs"], {})


class AlibiUpgradeTests(unittest.TestCase):
    def setUp(self):
        from app.games.alibi import Alibi

        self.g = make(Alibi, 5, seed=11)
        self.g.advance()  # briefing -> interrogation round 1
        self.killer = self.g.killer
        self.innocents = [p for p in self.g.player_ids if p != self.killer]

    def test_objection_on_the_killers_fake_slot_is_sustained(self):
        from app.games.alibi import OBJECTION_POINTS

        g, me = self.g, self.innocents[0]
        fake = next(s for s in sorted(g.fake) if s != g.murder_slot)
        g.handle(me, {"a": "object", "target": self.killer, "slot": fake})
        self.assertTrue(g.objections[0]["sustained"])
        self.assertEqual(g.scores()[me], OBJECTION_POINTS)
        self.assertIn((self.killer, fake), g.claims)  # their story is on the board now
        with self.assertRaises(GameError):
            g.handle(me, {"a": "object", "target": self.killer, "slot": 0})  # one per game

    def test_objection_on_an_honest_story_is_overruled(self):
        from app.games.alibi import OBJECTION_POINTS

        g, me = self.g, self.innocents[0]
        honest = next(p for p in self.innocents[1:] if not g.hazy or g.hazy[0] != p)
        g.handle(me, {"a": "object", "target": honest, "slot": 0})
        self.assertFalse(g.objections[0]["sustained"])
        self.assertEqual(g.scores()[me], -OBJECTION_POINTS)

    def test_plant_is_killer_only_once_secret_and_surfaces_with_the_next_clue(self):
        g = self.g
        target = self.innocents[0]
        with self.assertRaises(GameError):
            g.handle(target, {"a": "plant", "target": self.innocents[1], "slot": 0})
        with self.assertRaises(GameError):
            g.handle(self.killer, {"a": "plant", "target": self.killer, "slot": 0})
        clues_before, log_before = len(g.clues), len(g.log)
        g.handle(self.killer, {"a": "plant", "target": target, "slot": 2})
        with self.assertRaises(GameError):
            g.handle(self.killer, {"a": "plant", "target": target, "slot": 3})
        # Nothing shows yet: not on the board, not in the log, not in anyone else's view.
        self.assertEqual((len(g.clues), len(g.log)), (clues_before, log_before))
        for viewer in (*self.innocents, *SPECTATORS):
            view = g.view_for(viewer)
            self.assertIsNone(view["you"]["plant"])
            self.assertFalse(view["you"]["can_plant"])
        self.assertEqual(
            g.view_for(self.killer)["you"]["plant"], {"target": target, "slot": 2, "released": False}
        )
        g.advance()  # round 2: the real clue and the plant drop together
        drops = g.clues[clues_before:]
        self.assertEqual(len(drops), 2)
        self.assertEqual({tuple(sorted(c)) for c in drops}, {tuple(sorted(drops[0]))})  # same shape
        texts = [entry["text"] for entry in g.log[log_before:]]
        self.assertEqual(texts.count("New clue: a blurry camera feed was recovered."), 2)
        g.advance()
        g.advance()  # -> vote
        for p in g.player_ids:
            g.handle(p, {"a": "vote", "target": target if p != target else self.killer})
        self.assertIn("planted it to frame", " ".join(g.result["recap"]))
        self.assertEqual(g.result["planted"]["target"], target)
        self.assertIn("Framed!", [h["title"] for h in g.highlights()])

    def test_a_plant_in_the_last_round_still_surfaces_before_the_vote(self):
        g = self.g
        g.advance()
        g.advance()  # round 3
        n = len(g.clues)
        g.handle(self.killer, {"a": "plant", "target": self.innocents[0], "slot": 1})
        g.advance()  # -> vote
        self.assertEqual(g.phase, "vote")
        self.assertEqual(len(g.clues), n + 1)

    def test_no_new_moves_outside_interrogation(self):
        g = make(__import__("app.games.alibi", fromlist=["Alibi"]).Alibi, 4)
        with self.assertRaises(GameError):
            g.handle(g.player_ids[0], {"a": "object", "target": g.player_ids[1], "slot": 0})


class PriceUpgradeTests(unittest.TestCase):
    def setUp(self):
        from app.games.price import PriceIsWeird

        self.g = make(PriceIsWeird, 3, seed=5)

    def play_round(self, amount=1):
        for pid in self.g.player_ids:
            self.g.handle(pid, {"a": "guess", "amount": amount})

    def test_duel_scores_right_picks_and_keeps_picks_secret(self):
        from app.games.price import DUEL_POINTS

        g = self.g
        self.play_round()
        g.advance()  # reveal -> duel
        self.assertEqual(g.phase, "duel")
        a, b = g.duel_items[0]
        answer = 0 if a["price"] > b["price"] else 1
        before = g.scores()
        g.handle("p0", {"a": "duel", "pick": answer})
        for viewer in ("p1", "p2", *SPECTATORS):
            duel = g.view_for(viewer)["duel"]
            self.assertIsNone(duel["your_pick"])
            self.assertEqual(duel["locked"], ["p0"])
            self.assertNotIn("price", str(duel["items"]))  # prices hidden until it resolves
        g.handle("p1", {"a": "duel", "pick": 1 - answer})
        g.handle("p2", {"a": "duel", "pick": answer})  # last pick resolves it
        self.assertEqual(g.phase, "guess")
        self.assertEqual(g.scores()["p0"] - before["p0"], DUEL_POINTS)
        self.assertEqual(g.scores()["p1"], before["p1"])
        self.assertEqual(g.view_for("p1")["last_duel"]["right"], ["p0", "p2"])

    def test_duel_input_validation(self):
        g = self.g
        self.play_round()
        g.advance()
        for bad in (2, -1, True, "0", None):
            with self.assertRaises(GameError, msg=repr(bad)):
                g.handle("p0", {"a": "duel", "pick": bad})

    def test_showcase_is_three_prizes_one_total_and_a_triple_pot(self):
        from app.games.price import BASE_POT, SHOWCASE_POT

        g = self.g
        for _ in range(g.ROUNDS - 1):
            self.play_round()
            g.advance()
            g.advance()
        self.assertTrue(g.is_final)
        view = g.view_for("p0")
        self.assertEqual(len(view["showcase"]), 3)
        self.assertNotIn("showcase_prices", view)
        total = sum(x["price"] for x in g.showcase)
        self.assertEqual(g.items[-1]["price"], total)
        g.rollover = 0
        self.play_round(1)
        r = g.history[-1]
        self.assertEqual(r["true_price"], round(total * g.modifier))
        self.assertEqual(r["pot"], BASE_POT * SHOWCASE_POT if r["winner"] else 0)
        self.assertEqual(g.view_for("tv:x")["showcase_prices"], [x["price"] for x in g.showcase])

    def test_items_never_repeat_within_a_game(self):
        g = self.g
        names = [x["name"] for x in g.items[:-1] + g.showcase] + [
            x["name"] for pair in g.duel_items for x in pair
        ]
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
