"""Roulette Royale: bet rules, the House's cover, conservation, the commitment, rotation, validation."""

from __future__ import annotations

import json
import random
import unittest
from collections import Counter

from app.games import GameError, Player
from app.games.roulette import (
    ROUNDS,
    SPOT_BONUS,
    START_CHIPS,
    RouletteRoyale,
    commitment,
    payout,
    wins,
)

SPECTATORS = ("tv:screen", "au:fan")


def make(n=4, seed=1):
    g = RouletteRoyale([Player(id=f"p{i}", name=f"N{i}") for i in range(n)], rng=random.Random(seed))
    g.start()
    return g


class WheelTests(unittest.TestCase):
    def test_bet_types(self):
        self.assertTrue(wins("red", None, 1) and wins("black", None, 2) and wins("odd", None, 35))
        self.assertTrue(wins("low", None, 18) and wins("high", None, 19) and wins("dozen", 3, 36))
        self.assertFalse(wins("dozen", 1, 13))
        for kind in ("red", "black", "odd", "even", "low", "high"):
            self.assertFalse(wins(kind, None, 0), kind)  # zero beats every outside bet
        self.assertTrue(wins("number", 0, 0))
        self.assertEqual((payout("red"), payout("dozen"), payout("number")), (1, 2, 35))


class RouletteTests(unittest.TestCase):
    def test_the_house_takes_what_the_table_loses_and_chips_are_conserved(self):
        g = make(4)
        g.number = 7  # red, odd, low, first dozen
        bettors = [p for p in g.player_ids if p != g.house]
        g.handle(
            bettors[0],
            {
                "a": "lock",
                "bets": [{"kind": "red", "amount": 100}, {"kind": "number", "value": 7, "amount": 50}],
            },
        )
        g.handle(bettors[1], {"a": "lock", "bets": [{"kind": "even", "amount": 200}]})
        g.handle(bettors[2], {"a": "lock", "bets": [], "accuse": g.house})
        g.handle(
            g.house, {"a": "lock", "bets": [{"kind": "red", "amount": 50}], "accuse": bettors[0]}
        )  # decoy
        r = g.result
        self.assertEqual(r["net"][bettors[0]], 100 + 50 * 35)
        self.assertEqual(r["net"][bettors[1]], -200)
        self.assertEqual(r["house_net"], -(100 + 1750 - 200))
        self.assertEqual(r["spotted"], [bettors[2]])
        self.assertNotIn(g.house, r["bets"])  # the House's decoy bets never counted
        self.assertEqual(sum(g.chips.values()), 4 * START_CHIPS + SPOT_BONUS)

    def test_the_house_is_secret_until_the_spin(self):
        g = make(4)
        bettor = next(p for p in g.player_ids if p != g.house)
        before = g.view_for("tv:x")["locked_count"]
        g.handle(g.house, {"a": "lock", "bets": []})
        self.assertEqual(g.view_for("tv:x")["locked_count"], before + 1)  # the House locks in like anyone
        for viewer in (bettor, *SPECTATORS):
            view = g.view_for(viewer)
            self.assertFalse(view["you"]["is_house"])
            self.assertNotIn("result", view)
            text = json.dumps({k: v for k, v in view.items() if k not in ("players", "chips")})
            self.assertNotIn(g.house, text)
        self.assertTrue(g.view_for(g.house)["you"]["is_house"])

    def test_the_spin_matches_its_commitment(self):
        g = make(3)
        commit = g.view_for("p0")["commit"]
        g.advance()
        r = g.result
        self.assertEqual(commitment(r["number"], r["nonce"]), commit)

    def test_every_player_is_the_house_about_equally(self):
        g = make(3)
        houses = []
        for _ in range(ROUNDS):
            houses.append(g.house)
            g.advance()
            g.advance()
        self.assertTrue(g.finished)
        self.assertEqual(sorted(Counter(houses).values()), [2, 2, 2])
        self.assertTrue(all(a != b for a, b in zip(houses, houses[1:], strict=False)))
        self.assertEqual(g.scores(), {p: g.chips[p] - START_CHIPS for p in g.player_ids})

    def test_a_player_in_debt_can_still_lock_in_without_bets(self):
        g = make(3)
        p = next(x for x in g.player_ids if x != g.house)
        g.chips[p] = -700  # paid out big as the House last spin
        g.handle(p, {"a": "lock", "bets": []})
        self.assertIn(p, g.locked)
        with self.assertRaises(GameError):
            g.handle(next(x for x in g.player_ids if x not in (p, g.house)), {"a": "lock", "bets": "x"})

    def test_validation(self):
        g = make(3)
        p = next(x for x in g.player_ids if x != g.house)
        for bad in (
            [{"kind": "red", "amount": 75}],
            [{"kind": "number", "value": 37, "amount": 50}],
            [{"kind": "dozen", "value": 0, "amount": 50}],
            [{"kind": "corner", "amount": 50}],
            [{"kind": "red", "amount": 50}] * 4,
            "red",
        ):
            with self.assertRaises(GameError, msg=repr(bad)):
                g.handle(p, {"a": "lock", "bets": bad})
        g.chips[p] = 120
        with self.assertRaises(GameError):
            g.handle(
                p, {"a": "lock", "bets": [{"kind": "red", "amount": 100}, {"kind": "odd", "amount": 50}]}
            )
        with self.assertRaises(GameError):
            g.handle(p, {"a": "lock", "bets": [], "accuse": p})
        self.assertNotIn(p, g.locked)


if __name__ == "__main__":
    unittest.main()
