"""Web Push: the RFC 8291 worked example, a browser-side decryption round trip, VAPID tokens, and which
endpoints are allowed."""

from __future__ import annotations

import json
import struct
import unittest

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app import webpush as wp

# RFC 8291 section 5 (the "watermelon" example).
RFC = {
    "plaintext": b"When I grow up, I want to be a watermelon",
    "as_private": "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw",
    "ua_private": "q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94",
    "ua_public": "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
    "auth": "BTBZMqHH6r4Tts7J_aSIgg",
    "salt": "DGv6ra1nlYgDCS1FRnbzlw",
    "body": "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzA"
    "C8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN",
}


def private(b64: str) -> ec.EllipticCurvePrivateKey:
    return ec.derive_private_key(int.from_bytes(wp.unb64u(b64), "big"), ec.SECP256R1())


def decrypt(body: bytes, ua: ec.EllipticCurvePrivateKey, auth: bytes) -> bytes:
    """What the browser does: the receiving side of RFC 8291."""
    salt, rs, idlen = body[:16], *struct.unpack("!IB", body[16:21])
    as_point, cipher = body[21 : 21 + idlen], body[21 + idlen :]
    assert rs == 4096
    as_public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_point)
    ua_point = wp._point(ua.public_key())
    shared = ua.exchange(ec.ECDH(), as_public)
    ikm = wp._hkdf(auth, shared, b"WebPush: info\x00" + ua_point + as_point, 32)
    cek = wp._hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = wp._hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    plain = AESGCM(cek).decrypt(nonce, cipher, None)
    assert plain.endswith(b"\x02")
    return plain[:-1]


class EncryptionTests(unittest.TestCase):
    def test_the_rfc_8291_example(self):
        body = wp.encrypt(
            RFC["plaintext"],
            RFC["ua_public"],
            RFC["auth"],
            sender=private(RFC["as_private"]),
            salt=wp.unb64u(RFC["salt"]),
        )
        self.assertEqual(wp.b64u(body), RFC["body"])

    def test_a_browser_can_read_what_we_send(self):
        ua = ec.generate_private_key(ec.SECP256R1())
        auth = b"0123456789abcdef"
        payload = json.dumps({"title": "Game on", "url": "/clubs/x"}).encode()
        body = wp.encrypt(payload, wp.b64u(wp._point(ua.public_key())), wp.b64u(auth))
        self.assertEqual(decrypt(body, ua, auth), payload)
        again = wp.encrypt(payload, wp.b64u(wp._point(ua.public_key())), wp.b64u(auth))
        self.assertNotEqual(body, again)  # fresh key and salt every time


class VapidTests(unittest.TestCase):
    def test_the_key_is_stable_per_secret_and_the_token_verifies(self):
        a, b = (
            wp.Vapid.from_secret("k" * 40, "https://s.test"),
            wp.Vapid.from_secret("k" * 40, "https://s.test"),
        )
        self.assertEqual(a.public_key, b.public_key)
        self.assertNotEqual(a.public_key, wp.Vapid.from_secret("j" * 40, "https://s.test").public_key)
        self.assertEqual(len(wp.unb64u(a.public_key)), 65)

        header = a.header("https://fcm.googleapis.com/fcm/send/abc", now=1_000_000)
        token, key = header.removeprefix("vapid t=").split(", k=")
        self.assertEqual(key, a.public_key)
        head, claims, sig = token.split(".")
        self.assertEqual(
            json.loads(wp.unb64u(claims)),
            {"aud": "https://fcm.googleapis.com", "exp": 1_000_000 + 12 * 3600, "sub": "https://s.test"},
        )
        raw = wp.unb64u(sig)
        der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
        a.key.public_key().verify(der, f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))


class EndpointTests(unittest.TestCase):
    def test_only_push_services_over_https(self):
        good = [
            "https://fcm.googleapis.com/fcm/send/abc",
            "https://updates.push.services.mozilla.com/wpush/v2/abc",
            "https://web.push.apple.com/QGx",
            "https://db5p.notify.windows.com/w/?token=abc",
        ]
        bad = [
            "http://fcm.googleapis.com/fcm/send/abc",
            "https://fcm.googleapis.com.evil.test/x",
            "https://evilpush.apple.com.evil.test/x",
            "https://localhost/x",
            "https://169.254.169.254/latest",
            "https://user:pw@fcm.googleapis.com/x",
            "https://fcm.googleapis.com:8443/x",
            "https://push.apple.com.attacker.test/x",
            None,
            "https://fcm.googleapis.com/" + "a" * 1000,
        ]
        for url in good:
            self.assertTrue(wp.endpoint_ok(url), url)
        for url in bad:
            self.assertFalse(wp.endpoint_ok(url), url)

    def test_subscription_keys(self):
        ua = ec.generate_private_key(ec.SECP256R1())
        point = wp.b64u(wp._point(ua.public_key()))
        self.assertTrue(wp.keys_ok(point, wp.b64u(b"0123456789abcdef")))
        self.assertFalse(wp.keys_ok(point, wp.b64u(b"short")))
        self.assertFalse(wp.keys_ok("B" + "A" * 86, wp.b64u(b"0123456789abcdef")))  # not on the curve
        self.assertFalse(wp.keys_ok(7, "x"))
