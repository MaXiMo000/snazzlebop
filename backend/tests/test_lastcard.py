"""Last Card: the deck, matching, every action card, wild draw four challenges, stacking, the LAST CARD
call and catches, scoring, the clock, and that hands and the draw pile stay secret."""

from __future__ import annotations

import json
import random
import unittest
from collections import Counter

from app.games import GameError, Player
from app.games.lastcard import CARDS, LastCard, card_points

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def find(color: str, value: str, skip: int = 0) -> int:
    """The id of a card of this colour and value (the skip-th copy)."""
    return [i for i, (c, v) in enumerate(CARDS) if c == color and v == value][skip]


def make(n=3, seed=1, **opts):
    clock = Clock()
    g = LastCard(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=clock,
        options=opts or None,
    )
    g.start()
    return g, clock


def setup(g, hands: dict[int, list[int]], top: int, turn: int = 0, color: str | None = None):
    """Seat order p0, p1, ... ; give exact hands; put `top` on the pile; p<turn> to play."""
    g.order = list(g.player_ids)
    used = {c for h in hands.values() for c in h} | {top}
    g.deck = [c for c in range(len(CARDS)) if c not in used]
    g.discard = [top]
    g.hands = {f"p{i}": list(h) for i, h in hands.items()}
    for p in g.player_ids:
        g.hands.setdefault(p, [])
    g.color = color or CARDS[top][0]
    g.turn, g.direction = turn, 1
    g.pending, g.drawn = None, None
    g.protected, g.vulnerable = set(), set()


class DeckTests(unittest.TestCase):
    def test_the_deck_is_the_classic_108(self):
        self.assertEqual(len(CARDS), 108)
        counts = Counter(CARDS)
        for c in ("red", "yellow", "green", "blue"):
            self.assertEqual(counts[(c, "0")], 1)
            for v in ("1", "9", "skip", "reverse", "draw2"):
                self.assertEqual(counts[(c, v)], 2)
        self.assertEqual(counts[("wild", "wild")], 4)
        self.assertEqual(counts[("wild", "wild4")], 4)
        self.assertEqual([card_points(find("red", "7")), card_points(find("blue", "skip"))], [7, 20])
        self.assertEqual(card_points(find("wild", "wild4")), 50)

    def test_the_deal(self):
        g, _ = make(4)
        self.assertTrue(all(len(h) in (7, 9) for h in g.hands.values()))  # 9: a turned Draw Two
        self.assertNotEqual(CARDS[g.discard[0]][0], "wild")
        everything = [*g.deck, *g.discard, *(c for h in g.hands.values() for c in h)]
        self.assertEqual(sorted(everything), list(range(108)))


class PlayTests(unittest.TestCase):
    def test_matching(self):
        g, _ = make(3)
        r5, r7, b5, g2, w = (
            find("red", "5"),
            find("red", "7"),
            find("blue", "5"),
            find("green", "2"),
            find("wild", "wild"),
        )
        setup(g, {0: [r7, b5, g2, w, find("yellow", "1")]}, top=r5)
        self.assertTrue(g.playable("p0", r7))  # colour
        self.assertTrue(g.playable("p0", b5))  # number
        self.assertFalse(g.playable("p0", g2))
        self.assertTrue(g.playable("p0", w))
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "play", "card": g2})
        with self.assertRaises(GameError):
            g.handle("p1", {"a": "play", "card": r7})  # not their turn
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "play", "card": w})  # a wild needs a colour
        g.handle("p0", {"a": "play", "card": w, "color": "green"})
        self.assertEqual((g.color, g.current), ("green", "p1"))

    def test_skip_reverse_and_draw_two(self):
        g, _ = make(4)
        setup(
            g,
            {0: [find("red", "skip"), find("red", "1")], 3: [find("red", "reverse"), find("red", "2")]},
            top=find("red", "5"),
        )
        g.handle("p0", {"a": "play", "card": find("red", "skip")})
        self.assertEqual(g.current, "p2")
        g.turn = 3
        g.handle("p3", {"a": "play", "card": find("red", "reverse")})
        self.assertEqual((g.direction, g.current), (-1, "p2"))
        g.hands["p2"] = [find("red", "draw2"), find("blue", "3")]
        before = len(g.hands["p1"])
        g.handle("p2", {"a": "play", "card": find("red", "draw2")})
        self.assertEqual(len(g.hands["p1"]), before + 2)
        self.assertEqual(g.current, "p0")  # p1 drew two and lost the turn

    def test_reverse_is_a_skip_with_two_players(self):
        g, _ = make(2)
        setup(g, {0: [find("red", "reverse"), find("red", "1")]}, top=find("red", "5"))
        g.handle("p0", {"a": "play", "card": find("red", "reverse")})
        self.assertEqual(g.current, "p0")

    def test_draw_then_play_or_pass(self):
        g, _ = make(3)
        setup(g, {0: [find("blue", "1")]}, top=find("red", "5"))
        g.deck.remove(find("red", "9"))
        g.deck.append(find("red", "9"))  # the next card off the pile fits
        g.handle("p0", {"a": "draw"})
        self.assertEqual((g.current, g.drawn), ("p0", find("red", "9")))
        with self.assertRaises(GameError):
            g.handle("p0", {"a": "play", "card": find("blue", "1")})  # only the drawn card now
        g.handle("p0", {"a": "pass"})
        self.assertEqual(g.current, "p1")
        g.deck.remove(find("green", "2"))
        g.deck.append(find("green", "2"))  # doesn't fit: the turn just ends
        g.handle("p1", {"a": "draw"})
        self.assertEqual(g.current, "p2")


class WildFourTests(unittest.TestCase):
    def test_challenge_a_bluff(self):
        g, _ = make(3)
        w4 = find("wild", "wild4")
        setup(
            g, {0: [w4, find("red", "1"), find("blue", "2")], 1: [find("green", "3")]}, top=find("red", "5")
        )
        g.handle("p0", {"a": "play", "card": w4, "color": "blue"})  # illegal: p0 had red
        self.assertNotIn("legal", json.dumps(g.view_for("p1")["pending"]))
        g.handle("p1", {"a": "challenge"})
        self.assertEqual(len(g.hands["p0"]), 2 + 4)
        self.assertEqual((g.current, g.pending, len(g.hands["p1"])), ("p1", None, 1))

    def test_a_failed_challenge_costs_six(self):
        g, _ = make(3)
        w4 = find("wild", "wild4")
        setup(g, {0: [w4, find("blue", "2")], 1: [find("green", "3")]}, top=find("red", "5"))
        g.handle("p0", {"a": "play", "card": w4, "color": "blue"})  # legal: no red in hand
        g.handle("p1", {"a": "challenge"})
        self.assertEqual(len(g.hands["p1"]), 1 + 6)
        self.assertEqual(g.current, "p2")

    def test_accepting_draws_four(self):
        g, _ = make(3)
        w4 = find("wild", "wild4")
        setup(g, {0: [w4, find("blue", "2")], 1: [find("green", "3")]}, top=find("red", "5"))
        g.handle("p0", {"a": "play", "card": w4, "color": "blue"})
        self.assertFalse(g.playable("p1", find("green", "3")))
        g.handle("p1", {"a": "draw"})
        self.assertEqual((len(g.hands["p1"]), g.current), (5, "p2"))

    def test_stacking(self):
        g, _ = make(3, stacking="on")
        d1, d2 = find("red", "draw2"), find("blue", "draw2")
        setup(
            g,
            {0: [d1, find("red", "1")], 1: [d2, find("blue", "1")], 2: [find("green", "1")]},
            top=find("red", "5"),
        )
        g.handle("p0", {"a": "play", "card": d1})
        self.assertEqual(g.pending["n"], 2)
        g.handle("p1", {"a": "play", "card": d2})
        g.handle("p2", {"a": "draw"})
        self.assertEqual(len(g.hands["p2"]), 1 + 4)
        self.assertEqual(g.current, "p0")


class LastCardCallTests(unittest.TestCase):
    def test_caught_without_calling(self):
        g, _ = make(3)
        setup(g, {0: [find("red", "1"), find("red", "2")], 1: [find("blue", "9")]}, top=find("red", "5"))
        g.handle("p0", {"a": "play", "card": find("red", "1")})
        self.assertIn("p0", g.view_for("p2")["vulnerable"])
        g.handle("p2", {"a": "catch", "target": "p0"})
        self.assertEqual(len(g.hands["p0"]), 3)
        with self.assertRaises(GameError):
            g.handle("p2", {"a": "catch", "target": "p0"})

    def test_calling_protects_and_the_window_closes(self):
        g, _ = make(3)
        setup(
            g,
            {0: [find("red", "1"), find("red", "2")], 1: [find("red", "9"), find("blue", "9")]},
            top=find("red", "5"),
        )
        g.handle("p0", {"a": "last"})
        g.handle("p0", {"a": "play", "card": find("red", "1")})
        with self.assertRaises(GameError):
            g.handle("p1", {"a": "catch", "target": "p0"})
        # Without calling, the window shuts once the next player moves.
        setup(
            g,
            {0: [find("red", "1"), find("red", "2")], 1: [find("red", "9"), find("blue", "9")]},
            top=find("red", "5"),
        )
        g.handle("p0", {"a": "play", "card": find("red", "1")})
        g.handle("p1", {"a": "play", "card": find("red", "9")})
        with self.assertRaises(GameError):
            g.handle("p2", {"a": "catch", "target": "p0"})


class HandTests(unittest.TestCase):
    def test_going_out_scores_the_other_hands(self):
        g, _ = make(3)
        setup(
            g,
            {0: [find("red", "1")], 1: [find("blue", "9"), find("wild", "wild")], 2: [find("green", "skip")]},
            top=find("red", "5"),
        )
        g.handle("p0", {"a": "play", "card": find("red", "1")})
        self.assertEqual(g.phase, "hand_over")
        self.assertEqual(g.scores()["p0"], 9 + 50 + 20)
        v = g.view_for("p1")
        self.assertEqual(v["winner"], "p0")
        self.assertEqual(len(v["hands"]["p2"]), 1)  # every hand shown once it's over

    def test_a_final_draw_two_still_lands(self):
        g, _ = make(3)
        setup(g, {0: [find("red", "draw2")], 1: [find("blue", "9")]}, top=find("red", "5"))
        g.handle("p0", {"a": "play", "card": find("red", "draw2")})
        self.assertEqual(len(g.hands["p1"]), 3)
        self.assertEqual(g.scores()["p0"], sum(card_points(c) for c in g.hands["p1"]))

    def test_three_hands_and_the_clock(self):
        g, clock = make(3, hands="3")
        for _ in range(3):
            p = g.current
            setup(g, {int(p[1]): [find("red", "1")]}, top=find("red", "5"), turn=int(p[1]))
            g.handle(p, {"a": "play", "card": find("red", "1")})
            g.advance()  # the hand-over screen
        self.assertTrue(g.finished)
        self.assertEqual(len(g.view_for("tv:screen")["history"]), 3)

    def test_a_silent_turn_draws(self):
        g, clock = make(3)
        setup(g, {0: [find("blue", "1")]}, top=find("red", "5"))
        g.deck.remove(find("green", "2"))
        g.deck.append(find("green", "2"))
        g.set_deadline(30)
        clock.t = 31
        g.tick()
        self.assertEqual((len(g.hands["p0"]), g.current), (2, "p1"))


class SecrecyTests(unittest.TestCase):
    def test_hands_and_the_pile_stay_hidden(self):
        g, _ = make(4)
        mine = g.hands["p0"]
        for viewer in ["p1", *SPECTATORS]:
            v = g.view_for(viewer)
            self.assertNotIn("hands", v)
            ids = {c["id"] for c in (v["you"] or {}).get("hand", [])}
            self.assertFalse(ids & set(mine))
            self.assertEqual(v["counts"]["p0"], len(mine))
            self.assertNotIn("deck_cards", json.dumps(v))
            self.assertIsInstance(v["deck"], int)
        own = g.view_for("p0")
        self.assertEqual([c["id"] for c in own["you"]["hand"]], mine)
        self.assertIsNone(g.view_for("tv:screen")["you"])


if __name__ == "__main__":
    unittest.main()
