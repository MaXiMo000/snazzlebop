"""Authenticator codes against the RFCs' own test vectors (not codes this file computed), replay and
drift rules, derived secrets, the QR matrix and single-use backup codes."""

from __future__ import annotations

import base64
import unittest

from app import mfa

# RFC 4226 Appendix D and RFC 6238 Appendix B use this 20-byte ASCII key.
RFC_SECRET = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
RFC4226 = ["755224", "287082", "359152", "969429", "338314", "254676", "287922", "162583", "399871", "520489"]
# RFC 6238 Appendix B (SHA1): unix time -> 8-digit code; its last 6 digits are the 6-digit code.
RFC6238 = [
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
]


class TotpTests(unittest.TestCase):
    def test_hotp_matches_rfc4226(self):
        for counter, expected in enumerate(RFC4226):
            self.assertEqual(mfa.totp_at(RFC_SECRET, counter), expected)

    def test_totp_matches_rfc6238(self):
        for t, expected in RFC6238:
            self.assertEqual(mfa.totp_at(RFC_SECRET, t // 30), expected[-6:], t)
            self.assertIsNotNone(mfa.check_totp(RFC_SECRET, expected[-6:], now=t))

    def test_drift_window_and_replay(self):
        now = 1_700_000_000
        step = now // 30
        code = mfa.totp_at(RFC_SECRET, step - 1)  # the previous 30 s: a slow phone
        self.assertEqual(mfa.check_totp(RFC_SECRET, code, now), step - 1)
        self.assertIsNone(mfa.check_totp(RFC_SECRET, code, now, last_step=step - 1))  # used: refused
        self.assertIsNone(mfa.check_totp(RFC_SECRET, mfa.totp_at(RFC_SECRET, step - 2), now))  # too old
        self.assertIsNone(mfa.check_totp(RFC_SECRET, mfa.totp_at(RFC_SECRET, step + 2), now))  # too far ahead
        self.assertEqual(
            mfa.check_totp(RFC_SECRET, " " + mfa.totp_at(RFC_SECRET, step)[:3] + " 0", now), None
        )
        for bad in ("", "12345", "1234567", "abcdef", "12 34 5x"):
            self.assertIsNone(mfa.check_totp(RFC_SECRET, bad, now), bad)
        spaced = mfa.totp_at(RFC_SECRET, step)
        self.assertEqual(mfa.check_totp(RFC_SECRET, f"{spaced[:3]} {spaced[3:]}", now), step)  # "123 456"

    def test_secrets_are_derived_per_account_and_per_server(self):
        a, b = mfa.new_salt(), mfa.new_salt()
        self.assertNotEqual(a, b)
        s = mfa.totp_secret("k" * 40, a)
        self.assertEqual(s, mfa.totp_secret("k" * 40, a))  # stable: nothing to store
        self.assertNotEqual(s, mfa.totp_secret("k" * 40, b))
        self.assertNotEqual(s, mfa.totp_secret("j" * 40, a))  # the database alone isn't enough
        self.assertEqual(len(base64.b32decode(s + "=" * (-len(s) % 8))), 20)

    def test_uri_and_qr(self):
        uri = mfa.totp_uri(RFC_SECRET, "Ana_99")
        self.assertTrue(uri.startswith("otpauth://totp/Snazzlebop%3AAna_99?secret="))
        self.assertIn("issuer=Snazzlebop", uri)
        rows = mfa.qr_matrix(uri)
        self.assertEqual(len(rows), len(rows[0]))  # square
        self.assertTrue(all(set(r) <= {"0", "1"} for r in rows))
        self.assertEqual(rows[0], "0" * len(rows[0]))  # quiet zone
        self.assertEqual(rows[2][2:9], "1111111")  # a finder pattern's top edge


class BackupCodeTests(unittest.TestCase):
    def test_ten_single_use_codes_stored_only_as_keyed_hashes(self):
        key = "k" * 40
        codes, hashes = mfa.new_backup_codes(key)
        self.assertEqual(len(codes), 10)
        self.assertEqual(len(set(codes)), 10)
        self.assertTrue(all(c not in h for c in codes for h in hashes))
        left = mfa.take_backup_code(key, codes[3].lower().replace("-", " "), hashes)  # forgiving input
        self.assertIsNotNone(left)
        self.assertEqual(len(left), 9)
        self.assertIsNone(mfa.take_backup_code(key, codes[3], left))  # spent
        self.assertIsNone(mfa.take_backup_code(key, "AAAA-AAAA", left))
        self.assertIsNone(mfa.take_backup_code("j" * 40, codes[4], left))  # another server's key
