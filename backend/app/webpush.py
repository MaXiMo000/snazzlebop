"""Web Push without a push SDK: payload encryption (RFC 8291, aes128gcm) and VAPID (RFC 8292).

A browser that subscribes hands us an endpoint (a URL at its vendor's push service) plus two keys. To
send, we encrypt the payload to those keys and POST it to the endpoint with a signed VAPID token. The
push service never sees the content.

Safety:
- Endpoints are only ever URLs on the known push services (ALLOWED_HOSTS), over https, so a forged
  subscription can't make the server call anywhere else.
- The VAPID key pair is derived from the server's secret key, so it survives restarts without another
  setting. Rotating SECRET_KEY rotates it: old subscriptions then fail and are dropped.
- Payloads stay small and carry no personal data beyond a short text and a link on this site.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Chrome/Edge/Android (FCM), Firefox (Mozilla), Safari (Apple), Edge legacy (WNS).
ALLOWED_HOSTS = (
    "fcm.googleapis.com",
    "updates.push.services.mozilla.com",
    ".push.apple.com",
    ".notify.windows.com",
)
MAX_PAYLOAD = 3000  # well under the 4 KB push services accept once encrypted
RECORD_SIZE = 4096
TIMEOUT = 10.0
P256_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def endpoint_ok(endpoint: object) -> bool:
    """An https URL on a known push service, with no credentials or odd ports in it."""
    if not isinstance(endpoint, str) or len(endpoint) > 1000:
        return False
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443):
        return False
    return any(host == h or (h.startswith(".") and host.endswith(h)) for h in ALLOWED_HOSTS)


def keys_ok(p256dh: object, auth: object) -> bool:
    try:
        if not isinstance(p256dh, str) or not isinstance(auth, str) or len(p256dh) > 120 or len(auth) > 40:
            return False
        point, secret = unb64u(p256dh), unb64u(auth)
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), point)
        return len(point) == 65 and len(secret) == 16
    except (ValueError, TypeError):
        return False


# -- encryption (RFC 8291) ---------------------------------------------------------------------------
def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:length]


def _point(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def encrypt(
    payload: bytes,
    p256dh: str,
    auth: str,
    sender: ec.EllipticCurvePrivateKey | None = None,
    salt: bytes | None = None,
) -> bytes:
    """The request body for one push. `sender` and `salt` are fresh each time (fixed only in tests)."""
    ua_point, auth_secret = unb64u(p256dh), unb64u(auth)
    ua_public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_point)
    sender = sender or ec.generate_private_key(ec.SECP256R1())
    salt = salt or os.urandom(16)
    as_point = _point(sender.public_key())
    shared = sender.exchange(ec.ECDH(), ua_public)
    ikm = _hkdf(auth_secret, shared, b"WebPush: info\x00" + ua_point + as_point, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    body = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)  # one record: the last-record marker
    return salt + struct.pack("!IB", RECORD_SIZE, len(as_point)) + as_point + body


# -- VAPID (RFC 8292) --------------------------------------------------------------------------------
@dataclass(frozen=True)
class Vapid:
    key: ec.EllipticCurvePrivateKey
    subject: str  # a contact for the push services: the site's address

    @classmethod
    def from_secret(cls, secret: str, subject: str) -> Vapid:
        digest = hmac.new(secret.encode(), b"snazzlebop web push vapid v1", hashlib.sha256).digest()
        scalar = int.from_bytes(digest, "big") % (P256_ORDER - 1) + 1
        return cls(ec.derive_private_key(scalar, ec.SECP256R1()), subject)

    @property
    def public_key(self) -> str:
        """What the browser's pushManager.subscribe() needs as applicationServerKey."""
        return b64u(_point(self.key.public_key()))

    def header(self, endpoint: str, now: float | None = None) -> str:
        parts = urlsplit(endpoint)
        claims = {
            "aud": f"{parts.scheme}://{parts.netloc}",
            "exp": int((now or time.time()) + 12 * 3600),
            "sub": self.subject,
        }
        signing = (
            b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
            + "."
            + b64u(json.dumps(claims, separators=(",", ":")).encode())
        )
        r, s = decode_dss_signature(self.key.sign(signing.encode(), ec.ECDSA(hashes.SHA256())))
        token = signing + "." + b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        return f"vapid t={token}, k={self.public_key}"


class Gone(Exception):
    """The subscription no longer exists (the person turned notifications off or reset the browser)."""


def send(
    vapid: Vapid, endpoint: str, p256dh: str, auth: str, payload: dict[str, str], ttl: int = 3600
) -> None:
    """Deliver one push. Blocking: call it in a thread. Raises Gone for a dead subscription."""
    if not endpoint_ok(endpoint):
        raise Gone("not a push service")
    data = json.dumps(payload, separators=(",", ":")).encode()[:MAX_PAYLOAD]
    req = urllib.request.Request(  # noqa: S310 - endpoint_ok allows only https push services
        endpoint,
        data=encrypt(data, p256dh, auth),
        method="POST",
        headers={
            "Authorization": vapid.header(endpoint),
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": str(ttl),
            "Urgency": "normal",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310  # nosec B310
            resp.read(1024)
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            raise Gone(str(exc.code)) from None
        raise RuntimeError(f"push status {exc.code}") from None
