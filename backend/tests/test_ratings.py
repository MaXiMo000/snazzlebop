"""The rating model: winners rise, losers fall, uncertainty shrinks, ties are even, the day cap holds,
seasons and tiers."""

from __future__ import annotations

import unittest
import unittest.mock
from datetime import UTC, datetime

from app import ratings as R


class RateTests(unittest.TestCase):
    def test_a_duel(self):
        new = R.rate({"a": R.Rating(), "b": R.Rating()}, {"a": 1, "b": 2})
        self.assertGreater(new["a"].mu, R.MU)
        self.assertLess(new["b"].mu, R.MU)
        self.assertAlmostEqual(new["a"].mu - R.MU, R.MU - new["b"].mu, places=6)  # zero-sum when equal
        self.assertLess(new["a"].sigma, R.SIGMA)
        self.assertGreater(new["a"].display, 1000)

    def test_matches_the_reference_model(self):
        # OpenSkill's documented Plackett-Luce example (no added uncertainty): fresh a beats fresh b.
        with unittest.mock.patch.object(R, "TAU", 0.0):
            new = R.rate({"a": R.Rating(), "b": R.Rating()}, {"a": 1, "b": 2})
        self.assertAlmostEqual(new["a"].mu, 27.635231, places=5)
        self.assertAlmostEqual(new["a"].sigma, 8.065506, places=5)
        self.assertAlmostEqual(new["b"].mu, 22.364769, places=5)

    def test_ties_and_free_for_all(self):
        even = R.rate({"a": R.Rating(), "b": R.Rating()}, {"a": 1, "b": 1})
        self.assertAlmostEqual(even["a"].mu, R.MU, places=6)
        ffa = R.rate({p: R.Rating() for p in "abcd"}, R.ranks({"a": 9, "b": 5, "c": 5, "d": 0}))
        self.assertGreater(ffa["a"].mu, ffa["b"].mu)
        self.assertAlmostEqual(ffa["b"].mu, ffa["c"].mu, places=6)
        self.assertGreater(ffa["c"].mu, ffa["d"].mu)

    def test_an_upset_moves_more_than_the_expected_result(self):
        strong, weak = R.Rating(35, 3), R.Rating(20, 3)
        expected = R.rate({"s": strong, "w": weak}, {"s": 1, "w": 2})
        upset = R.rate({"s": strong, "w": weak}, {"s": 2, "w": 1})
        self.assertGreater(upset["w"].mu - weak.mu, expected["s"].mu - strong.mu)

    def test_the_day_cap(self):
        old = R.Rating()
        big = R.Rating(40, 4)
        held = R.capped(old, big, moved_today=100)
        self.assertEqual(held.display - old.display, R.DAY_CAP - 100)
        self.assertEqual(R.capped(old, big, moved_today=R.DAY_CAP).display, old.display)
        small = R.Rating(25.5, R.SIGMA)
        self.assertEqual(R.capped(old, small, 0), small)

    def test_tiers_and_provisional(self):
        self.assertEqual(R.tier(1600, 3), "Provisional")
        self.assertEqual(R.tier(900, 5), "Bronze")
        self.assertEqual(R.tier(1300, 9), "Gold")
        self.assertEqual(R.tier(2000, 9), "Diamond")

    def test_seasons(self):
        self.assertEqual(R.season_of(datetime(2026, 1, 5, tzinfo=UTC)), 1)
        self.assertEqual(R.season_of(datetime(2026, 3, 1, tzinfo=UTC)), 1)
        self.assertEqual(R.season_of(datetime(2026, 3, 2, tzinfo=UTC)), 2)
        start, end = R.season_dates(2)
        self.assertEqual((start.isoformat(), end.isoformat()), ("2026-03-02", "2026-04-26"))
        r = R.soft_reset(R.Rating(35, 2), 1)
        self.assertAlmostEqual(r.mu, 30)
        self.assertEqual(R.soft_reset(r, 0), r)


if __name__ == "__main__":
    unittest.main()
