"""Google sign-in's protocol checks: the signed state cookie, the authorization URL with PKCE, and ID
token verification (signature, issuer, audience, expiry, nonce) against a test key."""

from __future__ import annotations

import hashlib
import json
import time
import unittest
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app import oidc

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks(*pairs: tuple[str, rsa.RSAPrivateKey]) -> dict:
    out = []
    for kid, k in pairs:
        n = k.public_key().public_numbers()
        out.append(
            {
                "kty": "RSA",
                "kid": kid,
                "n": oidc.b64u(n.n.to_bytes((n.n.bit_length() + 7) // 8, "big")),
                "e": oidc.b64u(n.e.to_bytes(3, "big")),
            }
        )
    return {"keys": out}


def token(claims: dict, kid: str = "k1", key: rsa.RSAPrivateKey = KEY, alg: str = "RS256") -> str:
    head = oidc.b64u(json.dumps({"alg": alg, "kid": kid}).encode())
    body = oidc.b64u(json.dumps(claims).encode())
    sig = key.sign(f"{head}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{head}.{body}.{oidc.b64u(sig)}"


def good_claims(**over) -> dict:
    now = int(time.time())
    return {
        "iss": "https://accounts.google.com",
        "aud": "client-123",
        "sub": "1098765",
        "email": "ana@example.com",
        "email_verified": True,
        "nonce": "n-1",
        "iat": now,
        "exp": now + 3600,
    } | over


class StateTests(unittest.TestCase):
    def test_sealed_state_round_trips_and_resists_tampering(self):
        box = oidc.StateBox("s" * 40)
        a = oidc.new_attempt("link", 7)
        sealed = box.seal(a)
        self.assertEqual(box.open(sealed), a)
        body, mac = sealed.split(".")
        with self.assertRaises(oidc.OidcError):
            box.open(body + "." + mac[:-2] + "AA")
        with self.assertRaises(oidc.OidcError):
            oidc.StateBox("t" * 40).open(sealed)
        with self.assertRaises(oidc.OidcError):
            box.open(sealed, now=a.issued + oidc.STATE_SECONDS + 1)
        with self.assertRaises(oidc.OidcError):
            box.open("garbage")

    def test_the_authorization_url_carries_pkce(self):
        a = oidc.new_attempt("signin", None)
        url = oidc.auth_url("client-123", "https://s.test/api/auth/google/callback", a)
        q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.assertTrue(url.startswith(oidc.AUTH_URL))
        self.assertEqual(q["state"], a.state)
        self.assertEqual(q["nonce"], a.nonce)
        self.assertEqual(q["code_challenge_method"], "S256")
        self.assertEqual(q["code_challenge"], oidc.b64u(hashlib.sha256(a.verifier.encode()).digest()))
        self.assertNotIn(a.verifier, url)  # only the hash travels
        self.assertEqual(q["scope"], "openid email profile")


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.keys = oidc.KeySet(lambda: jwks(("k1", KEY)))

    def test_a_good_token(self):
        claims = oidc.verify(token(good_claims()), self.keys, "client-123", "n-1")
        self.assertEqual(claims["sub"], "1098765")

    def test_every_check_bites(self):
        bad = [
            token(good_claims(), key=OTHER),  # signed by someone else
            token(good_claims(), kid="nope"),  # a key Google doesn't have
            token(good_claims(), alg="HS256"),  # algorithm swap
            token(good_claims(iss="https://evil.test")),
            token(good_claims(aud="someone-else")),
            token(good_claims(exp=int(time.time()) - 3600)),
            token(good_claims(iat=int(time.time()) + 3600)),
            token(good_claims(nonce="n-2")),
            token(good_claims(sub="")),
            "not.a.token",
            "onlyone",
        ]
        for t in bad:
            with self.assertRaises(oidc.OidcError, msg=t[:40]):
                oidc.verify(t, self.keys, "client-123", "n-1")

    def test_the_audience_may_be_a_list_and_keys_are_cached(self):
        calls = []
        keys = oidc.KeySet(lambda: (calls.append(1), jwks(("k1", KEY)))[1])
        oidc.verify(token(good_claims(aud=["x", "client-123"])), keys, "client-123", "n-1")
        oidc.verify(token(good_claims()), keys, "client-123", "n-1")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
