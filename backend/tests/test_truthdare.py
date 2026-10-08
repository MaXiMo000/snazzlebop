"""Truth or Dare: fair turn order, choosing, voting, points, re-roll/chicken, secrecy of votes."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.truthdare import POINTS, STREAK_BONUS, TruthOrDare


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=3, seed=1, **opts):
    g = TruthOrDare(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)],
        rng=random.Random(seed),
        clock=Clock(),
        options=opts or None,
    )
    g.start()
    return g


def to_perform(g, choice="dare"):
    g.advance()  # spin -> choose
    g.handle(g.target, {"a": "choose", "choice": choice})


def vote_all(g, like=True):
    for p in g.player_ids:
        if p != g.target and g.phase == "vote":
            g.handle(p, {"a": "vote", "like": like})


class TruthOrDareTests(unittest.TestCase):
    def test_everyone_gets_the_same_number_of_turns(self):
        for length, per in (("quick", 1), ("standard", 2), ("marathon", 3)):
            g = make(5, length=length)
            self.assertEqual(len(g.order), 5 * per)
            self.assertTrue(all(g.order.count(p) == per for p in g.player_ids))
            self.assertTrue(all(a != b for a, b in zip(g.order, g.order[1:], strict=False)))

    def test_a_passed_dare_pays_and_a_failed_one_does_not(self):
        g = make()
        who = g.order[0]
        to_perform(g, "dare")
        self.assertTrue(g.prompt)
        g.handle(who, {"a": "done"})
        vote_all(g, like=True)
        self.assertEqual(g.phase, "result")
        self.assertEqual(g.scores()[who], POINTS["dare"])
        g.advance()
        nxt = g.target
        to_perform(g, "truth")
        g.handle(nxt, {"a": "done"})
        vote_all(g, like=False)
        self.assertEqual(g.scores()[nxt], 0)

    def test_only_the_target_acts_and_cannot_vote(self):
        g = make()
        g.advance()
        other = next(p for p in g.player_ids if p != g.target)
        with self.assertRaises(GameError):
            g.handle(other, {"a": "choose", "choice": "truth"})
        g.handle(g.target, {"a": "choose", "choice": "truth"})
        g.handle(g.target, {"a": "done"})
        with self.assertRaises(GameError):
            g.handle(g.target, {"a": "vote", "like": True})
        with self.assertRaises(GameError):
            g.handle(other, {"a": "vote", "like": "yes"})

    def test_reroll_and_chicken_work_once(self):
        g = make()
        who = g.order[0]
        to_perform(g)
        g.handle(who, {"a": "reroll"})
        with self.assertRaises(GameError):
            g.handle(who, {"a": "reroll"})
        g.handle(who, {"a": "chicken"})
        self.assertTrue(g.result["chicken"])
        self.assertEqual(g.scores()[who], 0)

    def test_three_dares_in_a_row_earn_the_daredevil_bonus(self):
        g = make(2, length="marathon")
        hero = g.order[0]
        earned = 0
        while not g.finished:
            if g.phase == "spin":
                g.advance()
            elif g.phase == "choose":
                g.handle(g.target, {"a": "choose", "choice": "dare"})
            elif g.phase == "perform":
                g.handle(g.target, {"a": "done"})
            elif g.phase == "vote":
                vote_all(g)
            elif g.phase == "result":
                if g.result["player"] == hero:
                    earned += g.result["points"] + g.result["bonus"]
                g.advance()
        self.assertEqual(earned, 3 * POINTS["dare"] + STREAK_BONUS)
        self.assertTrue(g.highlights())

    def test_timers_carry_a_silent_game_to_the_end(self):
        g = make(3, length="quick")
        for _ in range(100):
            if g.finished:
                break
            g.advance()
        self.assertTrue(g.finished)
        self.assertEqual(len(g.history), 3)
        for pid in [*g.player_ids, "tv:screen", "au:fan"]:  # the final screen renders for everyone
            v = g.view_for(pid)
            self.assertEqual((v["phase"], v["target"], v["round"]), ("final", None, 3))
            self.assertEqual(len(v["history"]), 3)

    def test_votes_stay_secret_until_the_result(self):
        g = make(4)
        to_perform(g)
        g.handle(g.target, {"a": "done"})
        voter = next(p for p in g.player_ids if p != g.target)
        g.handle(voter, {"a": "vote", "like": False})
        for pid in [*g.player_ids, "tv:screen", "au:fan"]:
            v = g.view_for(pid)
            self.assertEqual(v["voted"], 1)
            self.assertEqual(v["you_voted"], False if pid == voter else None)
            self.assertNotIn(voter + '": false', json.dumps(v))


if __name__ == "__main__":
    unittest.main()
