"""Sign in with Google: OpenID Connect, server side, without an SDK.

1. /api/auth/google/start sends the browser to Google with a random state, a nonce and a PKCE
   challenge; their secrets ride in a short-lived signed cookie (StateBox), never in our database.
2. Google sends the browser back to /api/auth/google/callback with a one-time code. We check the state,
   swap the code (plus the PKCE verifier and our client secret) for an ID token, and verify that token
   ourselves: Google's RS256 signature against its published keys, the issuer, the audience (our client
   id), the expiry and the nonce.
3. The account is found by Google's stable account id ("sub"), never by email: an existing account is
   linked to Google only from its own account page while signed in. A new Google sign-in makes a new
   account, using the email only if Google says it's verified and no other account has confirmed it.

No token ever appears in a URL we create; the callback sets the session cookie and redirects.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
EXCHANGE_URL = "https://oauth2.googleapis.com/token"
KEYS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
STATE_SECONDS = 600
SKEW = 60  # seconds of clock difference we tolerate
TIMEOUT = 10.0


class OidcError(Exception):
    """Anything wrong with a sign-in attempt; the message is safe to log, not to show."""


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# -- the round trip's secrets, in a signed cookie --------------------------------------------------
@dataclass(frozen=True)
class Attempt:
    state: str
    nonce: str
    verifier: str  # PKCE: the secret whose hash went to Google
    mode: str  # "signin" | "link"
    user_id: int | None  # who is linking (link mode)
    issued: float


class StateBox:
    """Seals an Attempt into a cookie value (HMAC-signed JSON) and opens it again within ten minutes."""

    def __init__(self, secret: str) -> None:
        self.key = hmac.new(secret.encode(), b"snazzlebop oidc state v1", hashlib.sha256).digest()

    def seal(self, a: Attempt) -> str:
        body = b64u(json.dumps(a.__dict__, separators=(",", ":")).encode())
        mac = b64u(hmac.new(self.key, body.encode(), hashlib.sha256).digest())
        return f"{body}.{mac}"

    def open(self, value: str, now: float | None = None) -> Attempt:
        try:
            body, mac = value.split(".")
            good = b64u(hmac.new(self.key, body.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(good, mac):
                raise OidcError("state signature")
            a = Attempt(**json.loads(unb64u(body)))
        except (ValueError, TypeError, KeyError) as exc:
            raise OidcError("state unreadable") from exc
        if (now or time.time()) - a.issued > STATE_SECONDS:
            raise OidcError("state expired")
        return a


def new_attempt(mode: str, user_id: int | None) -> Attempt:
    return Attempt(
        state=secrets.token_urlsafe(24),
        nonce=secrets.token_urlsafe(24),
        verifier=secrets.token_urlsafe(48),
        mode=mode,
        user_id=user_id,
        issued=time.time(),
    )


def auth_url(client_id: str, redirect_uri: str, a: Attempt) -> str:
    challenge = b64u(hashlib.sha256(a.verifier.encode()).digest())
    query = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": a.state,
        "nonce": a.nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(query)}"


# -- talking to Google (blocking: run in a thread) -------------------------------------------------
def _post_form(url: str, form: dict[str, str]) -> dict[str, Any]:
    req = urllib.request.Request(  # noqa: S310 - a fixed https Google URL
        url,
        data=urllib.parse.urlencode(form).encode(),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310  # nosec B310
            return json.loads(resp.read(100_000))
    except urllib.error.HTTPError as exc:
        raise OidcError(f"token endpoint {exc.code}") from None


def _get_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})  # noqa: S310 - fixed URL
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310  # nosec B310
        return json.loads(resp.read(200_000))


def exchange(code: str, verifier: str, client_id: str, client_secret: str, redirect_uri: str) -> str:
    """The one-time code (and PKCE verifier) for an ID token."""
    data = _post_form(
        EXCHANGE_URL,
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        },
    )
    token = data.get("id_token")
    if not isinstance(token, str):
        raise OidcError("no id_token")
    return token


class KeySet:
    """Google's signing keys, fetched when needed and kept for an hour."""

    def __init__(self, fetch: Callable[[], dict[str, Any]] | None = None) -> None:
        self.fetch = fetch or (lambda: _get_json(KEYS_URL))
        self.keys: dict[str, rsa.RSAPublicKey] = {}
        self.fetched = 0.0

    def get(self, kid: str) -> rsa.RSAPublicKey:
        if kid not in self.keys or time.time() - self.fetched > 3600:
            self.keys = {
                k["kid"]: rsa.RSAPublicNumbers(
                    int.from_bytes(unb64u(k["e"]), "big"), int.from_bytes(unb64u(k["n"]), "big")
                ).public_key()
                for k in self.fetch().get("keys", [])
                if k.get("kty") == "RSA" and "kid" in k
            }
            self.fetched = time.time()
        if kid not in self.keys:
            raise OidcError("unknown signing key")
        return self.keys[kid]


def verify(token: str, keys: KeySet, client_id: str, nonce: str, now: float | None = None) -> dict[str, Any]:
    """The ID token's claims, once its signature and every check pass."""
    try:
        head_b64, body_b64, sig_b64 = token.split(".")
        head = json.loads(unb64u(head_b64))
        claims = json.loads(unb64u(body_b64))
    except (ValueError, TypeError) as exc:
        raise OidcError("malformed token") from exc
    if head.get("alg") != "RS256":
        raise OidcError("unexpected algorithm")
    key = keys.get(str(head.get("kid", "")))
    try:
        key.verify(unb64u(sig_b64), f"{head_b64}.{body_b64}".encode(), padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        raise OidcError("bad signature") from None
    t = now or time.time()
    if claims.get("iss") not in ISSUERS:
        raise OidcError("wrong issuer")
    aud = claims.get("aud")
    if aud != client_id and not (isinstance(aud, list) and client_id in aud):
        raise OidcError("wrong audience")
    if not isinstance(claims.get("exp"), int | float) or claims["exp"] < t - SKEW:
        raise OidcError("expired")
    if isinstance(claims.get("iat"), int | float) and claims["iat"] > t + SKEW:
        raise OidcError("issued in the future")
    if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise OidcError("nonce mismatch")
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise OidcError("no subject")
    return claims


class Google:
    """Our Google client: off (enabled False) until both the client id and secret are set.
    Tests swap `exchange` and `keys` to stand in for Google."""

    def __init__(self, client_id: str, client_secret: str, site: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = f"{site.rstrip('/')}/api/auth/google/callback"
        self.keys = KeySet()
        self.exchange: Callable[[str, str], str] = lambda code, verifier: exchange(
            code, verifier, self.client_id, self.client_secret, self.redirect_uri
        )

    @property
    def enabled(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def authorize(self, a: Attempt) -> str:
        return auth_url(self.client_id, self.redirect_uri, a)

    def claims(self, code: str, a: Attempt) -> dict[str, Any]:
        """Blocking: swap the code and verify the ID token."""
        try:
            token = self.exchange(code, a.verifier)
        except (OSError, ValueError) as exc:
            raise OidcError(f"exchange failed: {type(exc).__name__}") from None
        return verify(token, self.keys, self.client_id, a.nonce)
