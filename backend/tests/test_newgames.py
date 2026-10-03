"""Telepathy Tax and Mole in the Mural: rules, scoring, validation and view_for secrecy (players + TV)."""

from __future__ import annotations

import random
import unittest

from app.games import GameError, Player
from app.games.mural import MoleInTheMural
from app.games.telepathy import TelepathyTax

TV = "tv:screen"


def make(cls, n, seed=1):
    players = [Player(id=f"p{i}", name=f"Name{i}") for i in range(n)]
    game = cls(players, rng=random.Random(seed), clock=lambda: 1000.0)
    game.start()
    return game, [p.id for p in players]


class TelepathyTests(unittest.TestCase):
    def test_matches_score_and_the_majority_is_taxed_to_zero(self):
        game, ids = make(TelepathyTax, 5)
        for pid, opt in zip(ids, [0, 0, 1, 1, 1], strict=True):
            game.handle(pid, {"a": "pick", "option": opt})
        r = game.view_for("p0")["result"]
        self.assertEqual(r["points"], {"p0": 100, "p1": 100, "p2": 0, "p3": 0, "p4": 0})  # 3 of 5 = taxed
        self.assertEqual(r["taxed"], [1])
        game2, ids2 = make(TelepathyTax, 6)
        for pid, opt in zip(ids2, [4, 4, 4, 2, 5, 5], strict=True):
            game2.handle(pid, {"a": "pick", "option": opt})
        r2 = game2.view_for("p0")["result"]
        self.assertEqual(r2["points"]["p0"], 200)  # 3 of 6 is exactly half: not taxed
        self.assertEqual(r2["points"]["p3"], 0)  # a lonely mind
        self.assertEqual(r2["points"]["p4"], 100)

    def test_picks_are_secret_until_the_reveal(self):
        game, ids = make(TelepathyTax, 4)
        game.handle("p0", {"a": "pick", "option": 3})
        for viewer in ["p1", "p2", TV]:
            v = game.view_for(viewer)
            self.assertNotIn("result", v)
            self.assertIsNone(v["your_pick"])
            self.assertEqual(v["locked"], ["p0"])  # who, never what
        self.assertEqual(game.view_for("p0")["your_pick"], 3)

    def test_input_validation(self):
        game, ids = make(TelepathyTax, 3)
        for bad in (6, -1, True, "1", None, 2.0):
            with self.assertRaises(GameError):
                game.handle("p0", {"a": "pick", "option": bad})
        game.handle("p0", {"a": "pick", "option": 1})
        with self.assertRaises(GameError):
            game.handle("p0", {"a": "pick", "option": 2})  # locked in
        with self.assertRaises(GameError):
            game.handle("ghost", {"a": "pick", "option": 1})
        with self.assertRaises(GameError):
            game.handle("p1", {"a": "nope"})

    def test_full_game_mind_meld_and_no_repeated_categories(self):
        game, ids = make(TelepathyTax, 4)
        for _ in range(TelepathyTax.ROUNDS):
            for pid, opt in zip(ids, [0, 0, 1, 2], strict=True):  # p0 and p1 always match
                game.handle(pid, {"a": "pick", "option": opt})
            game.advance()
        self.assertTrue(game.finished)
        final = game.view_for(TV)["final"]
        self.assertEqual(sorted(final["mind_meld"]["players"]), ["p0", "p1"])
        self.assertEqual(final["mind_meld"]["matches"], TelepathyTax.ROUNDS)
        # p0 always matches one other mind: 100 a round plus the streak bonus, except the
        # contrarian round, where a shared pick scores nothing and breaks the streak.
        want, streak = 0, 0
        for r in range(TelepathyTax.ROUNDS):
            if r == game.contrarian_round:
                streak = 0
                continue
            streak += 1
            want += 100 + (50 * min(streak - 1, 3) if streak >= 2 else 0)
        self.assertEqual(game.scores()["p0"], want)
        titles = [h["category"]["title"] for h in final["history"]]
        self.assertEqual(len(set(titles)), TelepathyTax.ROUNDS)

    def test_timer_reveals_with_whoever_picked(self):
        clock = [0.0]
        players = [Player(id=f"p{i}", name=f"N{i}") for i in range(3)]
        game = TelepathyTax(players, rng=random.Random(2), clock=lambda: clock[0])
        game.start()
        game.handle("p0", {"a": "pick", "option": 0})
        clock[0] += 31
        game.tick()
        self.assertEqual(game.phase, "reveal")
        self.assertEqual(game.view_for("p0")["result"]["points"], {"p0": 0})


def shares(game, i):
    t, h = game.mural[game.target], game.mural[i]
    return i != game.target and (h["color"] == t["color"] or h["kind"] == t["kind"])


class MuralTests(unittest.TestCase):
    def setUp(self):
        self.game, self.ids = make(MoleInTheMural, 5, seed=3)
        self.innocents = [i for i in self.ids if i != self.game.moles[0]]

    def hint_round(self, mole_tile=None):
        g = self.game
        for pid in self.ids:
            used = {h[pid] for h in g.hints if pid in h}
            if pid == g.moles[0]:
                tile = mole_tile if mole_tile is not None else next(i for i in range(16) if i not in used)
            else:
                tile = next(i for i in range(16) if shares(g, i) and i not in used)
            g.handle(pid, {"a": "hint", "tile": tile})

    def test_mural_always_gives_innocents_enough_hints(self):
        for seed in range(100):
            g, _ = make(MoleInTheMural, 8, seed=seed)
            self.assertEqual(len(g.mural), 16)
            self.assertGreaterEqual(sum(shares(g, i) for i in range(16)), 4)

    def test_nobody_but_the_innocents_ever_sees_the_painting(self):
        g = self.game
        g.advance()  # briefing -> hints
        for pid in self.innocents:
            self.assertEqual(g.view_for(pid)["you"]["target"], g.target)
        for viewer in (g.moles[0], TV):
            v = g.view_for(viewer)
            self.assertIsNone(v["you"]["target"])
            self.assertNotIn("result", v)
        self.assertTrue(g.view_for(g.moles[0])["you"]["is_mole"])
        for viewer in [*self.innocents, TV]:
            self.assertFalse(g.view_for(viewer)["you"]["is_mole"])
        self.assertNotIn("mole", {k for k in g.view_for(TV)})

    def test_hints_stay_secret_until_the_round_reveal(self):
        g = self.game
        g.advance()
        first = self.innocents[0]
        tile = next(i for i in range(16) if shares(g, i))
        g.handle(first, {"a": "hint", "tile": tile})
        for viewer in [*self.ids, TV]:
            v = g.view_for(viewer)
            self.assertEqual(v["hints"], [])  # nothing revealed yet
            self.assertEqual(v["hinted"], [first])  # who, never which tile
            self.assertEqual(v["your_hint"], tile if viewer == first else None)
        self.hint_round_rest(skip=first)
        self.assertEqual(g.view_for(TV)["hints"][0][first], tile)  # revealed together

    def hint_round_rest(self, skip):
        g = self.game
        for pid in self.ids:
            if pid == skip:
                continue
            tile = next(i for i in range(16) if (pid == g.moles[0] and i != g.target) or shares(g, i))
            g.handle(pid, {"a": "hint", "tile": tile})

    def test_innocents_must_hint_well_but_the_mole_is_never_corrected(self):
        g = self.game
        g.advance()
        innocent = self.innocents[0]
        unrelated = next((i for i in range(16) if i != g.target and not shares(g, i)), None)
        with self.assertRaises(GameError):
            g.handle(innocent, {"a": "hint", "tile": g.target})  # not the painting itself
        if unrelated is not None:
            with self.assertRaises(GameError):
                g.handle(innocent, {"a": "hint", "tile": unrelated})
        # The mole may pick anything, even the painting: refusing it would reveal the painting.
        g.handle(g.moles[0], {"a": "hint", "tile": g.target})
        for bad in (16, -1, True, "3"):
            with self.assertRaises(GameError):
                g.handle(innocent, {"a": "hint", "tile": bad})

    def test_caught_mole_gets_one_guess_and_scoring(self):
        for correct in (False, True):
            self.setUp()
            g = self.game
            g.advance()
            self.hint_round()
            self.hint_round()
            self.assertEqual(g.phase, "vote")
            for pid in self.ids:
                target = g.moles[0] if pid != g.moles[0] else self.innocents[0]
                g.handle(pid, {"a": "vote", "target": target})
            self.assertEqual(g.phase, "mole_guess")
            self.assertEqual(g.view_for(TV)["caught"], [g.moles[0]])  # the room knows who now
            self.assertIsNone(g.view_for(g.moles[0])["you"]["target"])  # still not the painting
            with self.assertRaises(GameError):
                g.handle(self.innocents[0], {"a": "guess", "tile": 0})  # only the mole guesses
            guess = g.target if correct else next(i for i in range(16) if i != g.target)
            g.handle(g.moles[0], {"a": "guess", "tile": guess})
            self.assertTrue(g.finished)
            r = g.view_for(TV)["result"]
            mole = g.moles[0]
            self.assertEqual(
                (r["moles"], r["target"], r["caught"], r["stole"]),
                ([mole], g.target, [mole], [mole] if correct else []),
            )
            if correct:
                self.assertEqual(g.scores()[g.moles[0]], 200)
                self.assertEqual(g.scores()[self.innocents[0]], 0)
            else:
                self.assertEqual(g.scores()[g.moles[0]], 0)
                self.assertEqual(g.scores()[self.innocents[0]], 200)  # 150 win + 50 for the right vote

    def test_mole_escapes_when_not_the_single_top_vote(self):
        g = self.game
        g.advance()
        self.hint_round()
        self.hint_round()
        for pid in self.ids:
            g.handle(pid, {"a": "vote", "target": next(o for o in self.innocents if o != pid)})
        self.assertTrue(g.finished)
        self.assertEqual(g.view_for(TV)["result"]["caught"], [])
        self.assertEqual(g.scores()[g.moles[0]], 300)


if __name__ == "__main__":
    unittest.main()
