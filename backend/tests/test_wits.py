"""Wager Wits: board odds, winning slot, payouts, author bonus, secrecy, validation."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.wits import AUTHOR_BONUS, CHIP_VALUE, ROUNDS, TOO_LOW_ODDS, WagerWits, board_odds

SPECTATORS = ("tv:screen", "au:fan")


def make(n=3, answer=206):
    g = WagerWits([Player(id=f"p{i}", name=f"N{i}") for i in range(n)], rng=random.Random(1))
    g.start()
    g.questions[0] = {"q": "How many bones are in an adult human body?", "a": answer, "unit": "bones"}
    return g


class WitsTests(unittest.TestCase):
    def test_board_odds(self):
        self.assertEqual(board_odds(1), [TOO_LOW_ODDS, 2])
        self.assertEqual(board_odds(3), [TOO_LOW_ODDS, 3, 2, 3])
        self.assertEqual(board_odds(8)[1:], [5, 4, 3, 2, 2, 3, 4, 5])

    def test_closest_without_going_over_wins_and_pays(self):
        g = make(3, answer=206)
        for pid, v in (("p0", 150), ("p1", 200), ("p2", 300)):
            g.handle(pid, {"a": "answer", "value": v})
        self.assertEqual([s["value"] for s in g.board], [None, 150, 200, 300])
        win = next(s for s in g.board if s["value"] == 200)
        g.handle("p0", {"a": "bet", "slots": [win["slot"], win["slot"]]})  # both chips on 200
        g.handle("p1", {"a": "bet", "slots": [win["slot"], 0]})
        g.handle("p2", {"a": "bet", "slots": [3, 3]})  # 300 went over
        self.assertEqual(g.result["slot"], win["slot"])
        self.assertEqual(g.scores()["p0"], 2 * CHIP_VALUE * win["odds"])
        self.assertEqual(g.scores()["p1"], CHIP_VALUE * win["odds"] + AUTHOR_BONUS)
        self.assertEqual(g.scores()["p2"], 0)

    def test_everyone_over_pays_the_lower_than_all_slot(self):
        g = make(2, answer=5)
        g.handle("p0", {"a": "answer", "value": 10})
        g.handle("p1", {"a": "answer", "value": 20})
        g.handle("p0", {"a": "bet", "slots": [0, 1]})
        g.handle("p1", {"a": "bet", "slots": [2, 2]})
        self.assertEqual(g.result["slot"], 0)
        self.assertEqual(g.scores(), {"p0": CHIP_VALUE * TOO_LOW_ODDS, "p1": 0})

    def test_shared_answers_share_a_slot_and_both_authors_get_the_bonus(self):
        g = make(3, answer=10)
        for pid in ("p0", "p1"):
            g.handle(pid, {"a": "answer", "value": 10})
        g.handle("p2", {"a": "answer", "value": 3})
        self.assertEqual(g.board[2]["by"], ["p0", "p1"])
        g.advance()  # nobody bets
        self.assertEqual(g.scores(), {"p0": AUTHOR_BONUS, "p1": AUTHOR_BONUS, "p2": 0})

    def test_secrecy(self):
        g = make(3, answer=777777)
        g.handle("p0", {"a": "answer", "value": 123456})
        for viewer in ("p1", *SPECTATORS):
            text = json.dumps(g.view_for(viewer))
            self.assertNotIn("123456", text)  # nobody else's answer before the board
            self.assertNotIn("777777", text)  # never the truth before the reveal
        self.assertEqual(g.view_for("p0")["you"]["answer"], 123456)
        g.advance()
        g.handle("p0", {"a": "bet", "slots": [1, 1]})
        for viewer in ("p1", *SPECTATORS):
            view = g.view_for(viewer)
            self.assertEqual(view["you"]["bets"], [])  # their own (empty) chips, never p0's
            self.assertEqual(view["bet_in"], ["p0"])
            self.assertNotIn("result", view)
            self.assertNotIn("777777", json.dumps(view))

    def test_validation(self):
        g = make(2)
        for bad in (-1, 10**9 + 1, 1.5, "12", True, None):
            with self.assertRaises(GameError, msg=repr(bad)):
                g.handle("p0", {"a": "answer", "value": bad})
        g.handle("p0", {"a": "answer", "value": 1})
        g.handle("p1", {"a": "answer", "value": 2})
        for bad in ([1], [1, 1, 1], [1, 9], "1,1", [True, 1]):
            with self.assertRaises(GameError, msg=repr(bad)):
                g.handle("p0", {"a": "bet", "slots": bad})

    def test_full_game_with_timeouts(self):
        g = make(3)
        for _ in range(ROUNDS * 3):
            g.advance()
        self.assertTrue(g.finished)
        self.assertEqual(len(g.history), ROUNDS)
        self.assertEqual(len({h["q"] for h in g.history}), ROUNDS)


if __name__ == "__main__":
    unittest.main()
