"""Presence and "up for a game" (pure, with a fake clock), and the notification rules that need no
database: settings, quiet hours."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from app import notify
from app.presence import MATCH_WINDOW, ONLINE_FOR, Presence


class Clock:
    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t


class PresenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        self.p = Presence(self.clock)

    def test_online_fades(self):
        self.p.touch(1)
        self.assertTrue(self.p.online(1))
        self.clock.t += ONLINE_FOR + 1
        self.assertFalse(self.p.online(1))
        self.assertFalse(self.p.online(2))

    def test_three_people_up_make_a_match(self):
        self.assertIsNone(self.p.up(1, 10, None, 60))
        self.assertIsNone(self.p.up(2, 10, "trivia", 30))
        self.assertIsNone(self.p.up(3, 99, None, 60))  # another club doesn't count
        match = self.p.up(4, 10, "trivia", 60)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual((match.game, sorted(match.members)), ("trivia", [1, 2, 4]))
        # A fourth person joins the open match instead of starting another.
        self.assertIsNone(self.p.up(5, 10, None, 30))
        self.assertIn(5, match.members)
        # The first to tap through opens the room; the next ones join it.
        self.assertEqual(self.p.take_room(10, 1), (match, True))
        match.room = "ABCDE"
        self.assertEqual(self.p.take_room(10, 2), (match, False))
        self.assertIsNone(self.p.take_room(10, 3))  # not one of them

    def test_different_picks_dont_match_each_other(self):
        self.p.up(1, 10, "trivia", 60)
        self.p.up(2, 10, "imposter", 60)
        self.assertIsNone(self.p.up(3, 10, "chess", 60))
        match = self.p.up(4, 10, "imposter", 60)
        self.assertIsNone(match)  # imposter has 2
        match = self.p.up(5, 10, None, 60)  # "any game" tips imposter to 3
        assert match is not None
        self.assertEqual((match.game, sorted(match.members)), ("imposter", [2, 4, 5]))

    def test_signals_run_out_and_old_ones_dont_count(self):
        self.p.up(1, 10, None, 30)
        self.clock.t += MATCH_WINDOW + 1
        self.p.up(2, 10, None, 60)
        self.assertIsNone(self.p.up(3, 10, None, 60))  # person 1 said so too long ago
        self.clock.t += 60 * 60 + 1
        self.assertIsNone(self.p.up_of(2))
        self.assertEqual(self.p.club_ups(10), [])

    def test_one_signal_per_person_and_cancelling(self):
        self.p.up(1, 10, None, 60)
        self.p.up(1, 11, None, 60)
        self.assertEqual([u.club_id for u in self.p.club_ups(11)], [11])
        self.assertEqual(self.p.club_ups(10), [])
        self.p.down(1)
        self.assertIsNone(self.p.up_of(1))
        with self.assertRaises(ValueError):
            self.p.up(1, 10, None, 45)


class ForgettingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.p = Presence(Clock())
        for uid in (1, 2, 3):
            self.p.up(uid, 10, None, 60)

    def test_a_closed_club_leaves_nothing_behind(self):
        self.assertIsNotNone(self.p.match_for(10))
        self.p.forget_club(10)
        self.assertIsNone(self.p.match_for(10))  # a new club given the same id starts clean
        self.assertEqual(self.p.club_ups(10), [])

    def test_leaving_the_club_and_deleting_the_account(self):
        self.p.leave_club(10, 2)
        self.assertIsNone(self.p.up_of(2))
        self.assertNotIn(2, self.p.match_for(10).members)
        self.p.touch(3)
        self.p.forget_user(3, [10])
        self.assertFalse(self.p.online(3))
        self.assertIsNone(self.p.match_for(10))


class PrefsTests(unittest.TestCase):
    def test_defaults_and_updates(self):
        base = notify.merged(None)
        self.assertEqual(base["types"], {"club_up": True, "invite": True})
        p = notify.clean_prefs({"hidden": True, "types": {"invite": False}, "tz": 330}, base)
        self.assertEqual(
            (p["hidden"], p["types"]["invite"], p["types"]["club_up"], p["tz"]), (True, False, True, 330)
        )
        p = notify.clean_prefs({"quiet": {"from": "23:00", "to": "07:30"}}, p)
        self.assertEqual(p["quiet"], {"from": "23:00", "to": "07:30"})
        self.assertTrue(p["hidden"])  # untouched settings stay

    def test_bad_settings(self):
        for bad in (
            {"hidden": "yes"},
            {"types": {"spam": True}},
            {"types": {"invite": 1}},
            {"quiet": {"from": "24:00", "to": "07:00"}},
            {"quiet": {"from": "07:00", "to": "07:00"}},
            {"tz": 900},
            {"tz": True},
            {"muted_clubs": [1]},
            [],
        ):
            with self.assertRaises(notify.PrefsError, msg=bad):
                notify.clean_prefs(bad, None)


class QuietTests(unittest.TestCase):
    def test_windows_wrap_midnight_and_follow_local_time(self):
        night = {"from": "23:00", "to": "08:00"}
        self.assertTrue(notify.in_quiet(night, 23 * 60))
        self.assertTrue(notify.in_quiet(night, 3 * 60))
        self.assertFalse(notify.in_quiet(night, 8 * 60))
        self.assertFalse(notify.in_quiet({"from": "13:00", "to": "14:00"}, 14 * 60))
        self.assertFalse(notify.in_quiet(None, 3 * 60))
        utc_2030 = datetime(2026, 10, 24, 20, 30, tzinfo=UTC)
        india = {"tz": 330, "quiet": night}  # 02:00 there
        self.assertTrue(notify.quiet_now(india, None, utc_2030))
        london = {"tz": 60, "quiet": night}  # 21:30 there
        self.assertFalse(notify.quiet_now(london, None, utc_2030))
        self.assertTrue(notify.quiet_now(london, {"from": "21:00", "to": "22:00"}, utc_2030))  # the club's


if __name__ == "__main__":
    unittest.main()
