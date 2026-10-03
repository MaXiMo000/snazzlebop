"""Mystery Box Auction: the deal, bidding rules, soft close, scoring, secrecy."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.boxes import BOX_COUNT, START_COINS, MysteryBoxes

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=4, seed=1):
    clock = Clock()
    g = MysteryBoxes(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)], rng=random.Random(seed), clock=clock
    )
    g.start()
    return g, clock


class BoxesTests(unittest.TestCase):
    def test_the_deal(self):
        g, _ = make(8)
        values = [c["value"] for c in g.contents]
        self.assertEqual(len(values), BOX_COUNT)
        self.assertEqual(sum(v < 0 for v in values), 2)
        self.assertEqual(values.count(0), 1)
        # 8 players over 6 boxes: everyone peeks one, every box is peeked by someone.
        self.assertEqual(set(g.peeks.values()), set(range(BOX_COUNT)))

    def test_bidding_rules(self):
        g, _ = make()
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "bid", "amount": 50})  # still peeking
        g.advance()
        g.handle("p0", {"a": "bid", "amount": 50})
        for bad in (55, 50, True, "70", None, START_COINS + 10):
            with self.assertRaises(GameError, msg=repr(bad)):
                g.handle("p1", {"a": "bid", "amount": bad})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "bid", "amount": 100})  # already on top
        g.handle("p1", {"a": "bid", "amount": 60})
        self.assertEqual(g.high, {"player": "p1", "amount": 60})

    def test_cannot_bid_more_than_your_coins(self):
        g, _ = make()
        g.coins["p0"] = 40
        g.advance()
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "bid", "amount": 50})

    def test_soft_close_extends_a_late_bid(self):
        g, clock = make()
        g.advance()
        clock.t += 14
        g.handle("p0", {"a": "bid", "amount": 10})
        self.assertAlmostEqual(g.remaining(), 6.0)
        clock.t += 5
        g.tick()
        self.assertEqual(g.phase, "auction")
        clock.t += 1
        g.tick()
        self.assertEqual(g.phase, "sold")

    def test_scoring_and_coins(self):
        g, _ = make()
        g.advance()
        g.handle("p2", {"a": "bid", "amount": 120})
        g.advance()  # hammer
        box = g.contents[0]
        self.assertEqual(g.scores()["p2"], box["value"] - 120)
        self.assertEqual(g.coins["p2"], START_COINS - 120)
        self.assertEqual(g.sold[0]["winner"], "p2")
        g.advance()  # next box, nobody bids
        g.advance()
        self.assertIsNone(g.sold[1]["winner"])
        for _ in range(BOX_COUNT - 2):
            g.advance()
            g.advance()
        self.assertFalse(g.finished)  # the last box is still on show
        g.advance()
        self.assertTrue(g.finished)

    def test_contents_and_peeks_are_secret(self):
        g, _ = make(4)
        g.advance()
        for viewer in ("p0", "p1", *SPECTATORS):
            view = g.view_for(viewer)
            peek = g.peeks.get(viewer)
            shown = json.dumps(view)
            for i, c in enumerate(g.contents):
                if i != peek:
                    self.assertNotIn(c["name"], shown, (viewer, i))
            if peek is None:
                self.assertIsNone(view["you"]["peek"])
            else:
                self.assertEqual(view["you"]["peek"]["box"], peek)
        g.advance()  # box A sold: its contents are public now
        self.assertIn(g.contents[0]["name"], json.dumps(g.view_for("tv:screen")))

    def test_claims_are_one_per_box(self):
        g, _ = make()
        g.advance()
        g.handle("p0", {"a": "say", "line": 1})
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "say", "line": 2})
        with self.assertRaises(GameError):
            g.handle("p1", {"a": "say", "line": 99})
        self.assertIn("p0", g.view_for("p1")["claims"])

    def test_peek_card_shows_another_unsold_box(self):
        g, _ = make(3)
        msg = g.peek("p0")
        self.assertIsNotNone(msg)
        extra = g.extra_peeks["p0"]
        self.assertNotEqual(extra, g.peeks["p0"])
        self.assertIn(g.contents[extra]["name"], msg)
        self.assertEqual(g.view_for("p0")["you"]["extra"]["box"], extra)
        self.assertIsNone(g.view_for("p1")["you"]["extra"])

    def test_highlights_after_a_bomb_sale(self):
        g, _ = make(4)
        bomb = next(i for i, c in enumerate(g.contents) if c["value"] < 0)
        buyer = next(p for p in g.player_ids if g.peeks[p] != bomb)
        g.advance()
        for i in range(BOX_COUNT):
            if i == bomb:
                g.handle(buyer, {"a": "bid", "amount": 10})
            g.advance()
            g.advance()
        self.assertTrue(g.finished)
        self.assertIn("Kaboom", [h["title"] for h in g.highlights()])


if __name__ == "__main__":
    unittest.main()
