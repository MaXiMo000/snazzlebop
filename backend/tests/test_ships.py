"""Battleships: legal fleets, placing, firing, turns, sinking, winning, and hidden layouts."""

from __future__ import annotations

import json
import random
import unittest

from app.games import GameError, Player
from app.games.ships import FLEET, HIT, SINK, SIZE, WIN, Battleships, place

SPECTATORS = ("tv:screen", "au:fan")


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(n=2, seed=1):
    clock = Clock()
    g = Battleships(
        [Player(id=f"p{i}", name=f"N{i}") for i in range(n)], rng=random.Random(seed), clock=clock
    )
    g.start()
    return g, clock


def lock_in(g):
    for side in (0, 1):
        g.handle(g.sides[side][0], {"a": "ready"})


def water(g, side):
    ships = {c for s in g.fleets[side] for c in s}
    return next(c for c in range(SIZE * SIZE) if c not in ships and c not in g.shots[side])


class PlaceTests(unittest.TestCase):
    def test_random_fleets_are_legal(self):
        for seed in range(200):
            ships = place(random.Random(seed))
            self.assertEqual(sorted(len(s) for s in ships), sorted(FLEET))
            cells = [c for s in ships for c in s]
            self.assertEqual(len(cells), len(set(cells)))
            for s in ships:
                rows = {c // SIZE for c in s}
                cols = {c % SIZE for c in s}
                self.assertTrue(all(0 <= c < SIZE * SIZE for c in s))
                self.assertTrue(len(rows) == 1 or len(cols) == 1)  # a straight line
                line = sorted(cols) if len(rows) == 1 else sorted(rows)
                self.assertEqual(line, list(range(line[0], line[0] + len(s))))  # no gaps, no wrapping

    def test_shuffle_then_lock(self):
        g, _ = make(2)
        a = g.sides[0][0]
        before = json.dumps(g.fleets[0])
        seen = {before}
        for _ in range(5):
            g.handle(a, {"a": "shuffle"})
            seen.add(json.dumps(g.fleets[0]))
        self.assertGreater(len(seen), 2)
        g.handle(a, {"a": "ready"})
        with self.assertRaises(GameError):
            g.handle(a, {"a": "shuffle"})
        with self.assertRaises(GameError):
            g.handle(a, {"a": "fire", "cell": 0})
        self.assertEqual(g.phase, "place")
        g.handle(g.sides[1][0], {"a": "ready"})
        self.assertEqual(g.phase, "battle")

    def test_the_clock_starts_the_battle(self):
        g, clock = make(2)
        clock.t += 41
        g.tick()
        self.assertEqual(g.phase, "battle")


class BattleTests(unittest.TestCase):
    def test_hit_fires_again_miss_passes(self):
        g, _ = make(2)
        lock_in(g)
        side = g.turn
        shooter = g._shooter()
        target = 1 - side
        ship = g.fleets[target][0]
        g.handle(shooter, {"a": "fire", "cell": ship[0]})
        self.assertEqual((g.last["result"], g.turn), ("hit", side))
        self.assertEqual(g.round_scores[shooter], HIT)
        with self.assertRaises(GameError):
            g.handle(shooter, {"a": "fire", "cell": ship[0]})  # same square
        for cell in ship[1:]:
            g.handle(shooter, {"a": "fire", "cell": cell})
        self.assertEqual(g.last["result"], "sunk")
        self.assertEqual(g.round_scores[shooter], HIT * len(ship) + SINK)
        g.handle(shooter, {"a": "fire", "cell": water(g, target)})
        self.assertEqual((g.last["result"], g.turn), ("miss", target))
        with self.assertRaises(GameError):
            g.handle(shooter, {"a": "fire", "cell": water(g, target)})  # not your shot now

    def test_bad_input(self):
        g, _ = make(2)
        lock_in(g)
        shooter = g._shooter()
        for bad in (None, -1, 64, 3.5, "7", True, [1]):
            with self.assertRaises(GameError):
                g.handle(shooter, {"a": "fire", "cell": bad})
        with self.assertRaises(GameError):
            g.handle(shooter, {"a": "torpedo"})
        with self.assertRaises(GameError):
            g.handle("stranger", {"a": "fire", "cell": 1})

    def test_sinking_everything_wins(self):
        g, _ = make(2)
        lock_in(g)
        side = g.turn
        shooter = g._shooter()
        for ship in g.fleets[1 - side]:
            for cell in ship:
                g.handle(shooter, {"a": "fire", "cell": cell})
        self.assertTrue(g.finished)
        self.assertEqual(g.winner, side)
        cells = sum(FLEET)
        self.assertEqual(g.round_scores[shooter], cells * HIT + len(FLEET) * SINK + WIN)
        view = g.view_for("tv:screen")
        self.assertEqual(view["winner"], side)
        self.assertIsNotNone(view["boards"][side]["ships"])  # the survivors are shown at the end

    def test_teams_share_a_fleet_and_take_turns(self):
        g, _ = make(5)
        self.assertEqual(sorted(len(s) for s in g.sides), [2, 3])
        lock_in(g)
        side = g.turn
        first = g._shooter()
        self.assertIn(first, g.sides[side])
        mate = next(p for p in g.sides[side] if p != first)
        with self.assertRaises(GameError):
            g.handle(mate, {"a": "fire", "cell": 0})
        g.handle(first, {"a": "fire", "cell": g.fleets[1 - side][0][0]})  # a hit: same side, next gun
        self.assertEqual(g.turn, side)
        self.assertNotEqual(g._shooter(), first)
        self.assertEqual(g.chat_team(first), (f"fleet:{side}", ("Fleet Tangerine", "Fleet Teal")[side]))
        solo, _ = make(2)
        self.assertIsNone(solo.chat_team("p0"))

    def test_timeouts_and_random_games_finish(self):
        for seed in range(12):
            g, clock = make(random.Random(seed).randint(2, 8), seed)
            for _ in range(400):
                if g.finished:
                    break
                clock.t += 50
                g.tick()
            self.assertTrue(g.finished, seed)
            loser = 1 - g.winner
            self.assertTrue(all(c in g.shots[loser] for s in g.fleets[loser] for c in s))


class SecrecyTests(unittest.TestCase):
    def leaked(self, g, viewer, side):
        """Does this viewer's frame give away an unhit ship square of that side?"""
        board = g.view_for(viewer)["boards"][side]
        return board["ships"] is not None

    def test_only_your_own_side_sees_your_ships(self):
        g, _ = make(4)
        for phase in ("place", "battle"):
            for pid in g.player_ids:
                mine = g.side_of[pid]
                self.assertTrue(self.leaked(g, pid, mine))
                self.assertFalse(self.leaked(g, pid, 1 - mine))
                self.assertEqual(g.view_for(pid)["boards"][mine]["ships"], g.fleets[mine])
            for viewer in SPECTATORS:
                self.assertFalse(self.leaked(g, viewer, 0) or self.leaked(g, viewer, 1))
                self.assertIsNone(g.view_for(viewer)["you"])
            if phase == "place":
                lock_in(g)

    def test_shots_show_results_and_sunk_ships_only(self):
        g, _ = make(2)
        lock_in(g)
        side = g.turn
        shooter, target = g._shooter(), 1 - g.turn
        ship = min(g.fleets[target], key=len)
        g.handle(shooter, {"a": "fire", "cell": ship[0]})
        board = g.view_for(shooter)["boards"][target]
        self.assertEqual(board["shots"], {str(ship[0]): "hit"})
        self.assertEqual((board["sunk"], board["ships"], board["afloat"]), ([], None, len(FLEET)))
        g.handle(shooter, {"a": "fire", "cell": ship[1]})
        for viewer in [shooter, *SPECTATORS]:
            board = g.view_for(viewer)["boards"][target]
            self.assertEqual(board["sunk"], [ship])
            self.assertEqual(board["afloat"], len(FLEET) - 1)
            unhit = {c for s in g.fleets[target] for c in s} - set(ship)
            blob = json.dumps(board)
            self.assertIsNone(board["ships"])
            self.assertTrue(all(str(c) not in board["shots"] for c in unhit))
            self.assertEqual(json.loads(blob)["shots"].keys(), {str(c) for c in ship})
        self.assertEqual(g.turn, side)


if __name__ == "__main__":
    unittest.main()
