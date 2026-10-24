"""Club policy: who may act on whom, names, settings and invite codes."""

from __future__ import annotations

import unittest

from app.clubs import policy as p

ROLES = p.ROLES


class RoleTests(unittest.TestCase):
    def test_editing_and_inviting(self):
        self.assertEqual([r for r in ROLES if p.may_edit(r)], ["owner", "admin"])
        self.assertEqual([r for r in ROLES if p.may_invite(r)], ["owner", "admin", "moderator"])

    def test_removing_only_works_downwards(self):
        allowed = {(a, t) for a in ROLES for t in ROLES if p.may_remove(a, t)}
        self.assertEqual(
            allowed,
            {
                ("owner", "admin"),
                ("owner", "moderator"),
                ("owner", "member"),
                ("admin", "moderator"),
                ("admin", "member"),
                ("moderator", "member"),
            },
        )
        self.assertFalse(p.may_remove("member", "member"))
        self.assertFalse(p.may_remove("bogus", "member"))

    def test_roles_are_given_only_below_your_own(self):
        self.assertTrue(p.may_set_role("owner", "member", "admin"))
        self.assertTrue(p.may_set_role("owner", "admin", "member"))
        self.assertTrue(p.may_set_role("admin", "member", "moderator"))
        self.assertFalse(p.may_set_role("admin", "member", "admin"))  # not as high as your own
        self.assertFalse(p.may_set_role("admin", "admin", "member"))  # not someone level with you
        self.assertFalse(p.may_set_role("moderator", "member", "moderator"))
        self.assertFalse(p.may_set_role("owner", "member", "owner"))  # ownership moves by transfer
        self.assertFalse(p.may_set_role("owner", "member", "king"))


class TextTests(unittest.TestCase):
    def test_names(self):
        self.assertEqual(p.clean_name("  Hostel   4  Quiz  "), "Hostel 4 Quiz")
        for bad in ("ab", "x" * 41, "nul\x00byte", None, 7):
            with self.assertRaises(p.PolicyError):
                p.clean_name(bad)
        self.assertEqual(p.clean_about(None), "")
        with self.assertRaises(p.PolicyError):
            p.clean_about("x" * 201)

    def test_slugs_are_readable_and_distinct(self):
        a, b = p.slug_for("Hostel 4: Quiz Crew!"), p.slug_for("Hostel 4: Quiz Crew!")
        self.assertTrue(a.startswith("hostel-4-quiz-crew-"))
        self.assertNotEqual(a, b)
        self.assertTrue(p.slug_for("🎲🎲🎲").startswith("club-"))
        self.assertRegex(p.slug_for("Ünïcode Café"), r"^unicode-cafe-[a-z0-9]{4}$")


class RulesTests(unittest.TestCase):
    def test_defaults_and_valid_settings(self):
        self.assertEqual(p.clean_rules(None), p.DEFAULT_RULES)
        r = p.clean_rules(
            {"games": ["trivia", "imposter", "trivia"], "quiet": {"from": "23:00", "to": "08:00"}}
        )
        self.assertEqual(r["games"], ["imposter", "trivia"])
        self.assertTrue(r["chat"])

    def test_bad_settings(self):
        for bad in (
            {"games": ["nope"]},
            {"games": "trivia"},
            {"chat": "yes"},
            {"quiet": {"from": "25:00", "to": "08:00"}},
            {"quiet": {"from": "08:00", "to": "08:00"}},
            {"quiet": {"from": "08:00"}},
            {"colour": "red"},
            [],
        ):
            with self.assertRaises(p.PolicyError, msg=bad):
                p.clean_rules(bad)


class InviteTests(unittest.TestCase):
    def test_codes_and_hashes(self):
        code = p.new_invite_code()
        self.assertEqual(len(code), 10)
        self.assertNotIn("0", code)
        h = p.hash_invite("k" * 40, code)
        self.assertEqual(h, p.hash_invite("k" * 40, f" {code[:5].lower()}-{code[5:]} "))  # forgiving input
        self.assertNotEqual(h, p.hash_invite("j" * 40, code))
        self.assertNotIn(code, h)

    def test_clamp(self):
        self.assertEqual(p.clamp(None, p.INVITE_DAYS, 7, "Days"), 7)
        self.assertEqual(p.clamp(30, p.INVITE_DAYS, 7, "Days"), 30)
        for bad in (0, 31, True, "7"):
            with self.assertRaises(p.PolicyError):
                p.clamp(bad, p.INVITE_DAYS, 7, "Days")
