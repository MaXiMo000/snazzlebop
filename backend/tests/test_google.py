"""Sign in with Google over HTTP, with Google stood in for: off until configured, new accounts,
returning sign-ins, never matching an existing account by email, linking and unlinking, and accounts
with no password confirming changes by a fresh sign-in."""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app import oidc  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.test_account_email import confirmed, outbox  # noqa: E402
from tests.test_api import settings  # noqa: E402
from tests.test_mfa_accounts import now_code  # noqa: E402
from tests.test_oidc import KEY, good_claims, jwks, token  # noqa: E402

PW = "correct horse battery"


@pytest.fixture()
def client(tmp_path):
    s = settings(
        tmp_path,
        rate_auth_burst=1000,
        public_url="https://snazzlebop.test",
        google_client_id="client-123",
        google_client_secret="shh",
    )
    app = create_app(s)
    app.state.mailer.keep = True
    app.state.google.keys = oidc.KeySet(lambda: jwks(("k1", KEY)))
    with TestClient(app) as c:
        yield c


def google_says(client, **claims):
    """Make Google answer the next exchange with these claims (plus the right nonce)."""

    def exchange(code, verifier):
        return token(good_claims(nonce=client.nonce, **claims))

    client.app.state.google.exchange = exchange


def go(client, mode="signin", **claims) -> str:
    """The whole round trip; returns the outcome the account page is sent."""
    r = client.get(f"/api/auth/google/start?mode={mode}", follow_redirects=False)
    assert r.status_code == 303
    where = r.headers["location"]
    if not where.startswith(oidc.AUTH_URL):
        return parse_qs(urlsplit(where).query)["google"][0]
    q = {k: v[0] for k, v in parse_qs(urlsplit(where).query).items()}
    assert q["redirect_uri"] == "https://snazzlebop.test/api/auth/google/callback"
    client.nonce = q["nonce"]
    google_says(client, **claims)
    r = client.get(f"/api/auth/google/callback?code=abc&state={q['state']}", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/account?google=")
    return parse_qs(urlsplit(r.headers["location"]).query)["google"][0]


def test_off_until_configured(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        assert c.get("/api/me").json()["google"] is False
        r = c.get("/api/auth/google/start", follow_redirects=False)
        assert r.headers["location"] == "/account?google=off"


def test_a_new_google_account_then_signing_in_again(client):
    assert client.get("/api/me").json()["google"] is True
    assert go(client, given_name="Ana") == "welcome"
    me = client.get("/api/me").json()["user"]
    assert me["username"].startswith("Ana_")
    assert me["has_password"] is False
    assert me["email"] == "ana@example.com" and me["email_verified"] is True
    ids = client.get("/api/me/identities").json()
    assert ids == {"google": {"email": "ana@example.com"}, "google_available": True, "has_password": False}

    client.post("/api/auth/logout")
    assert client.get("/api/me").json()["user"] is None
    assert go(client) == "signed_in"
    assert client.get("/api/me").json()["user"]["username"] == me["username"]


def test_an_unverified_google_email_is_not_used(client):
    assert go(client, sub="777", email="who@example.com", email_verified=False) == "welcome"
    assert client.get("/api/me").json()["user"]["email"] is None


def test_never_matched_to_an_existing_account_by_email(client):
    confirmed(client)  # Ana_99 owns ana@example.com
    client.post("/api/auth/logout")
    assert go(client) == "email_taken"
    assert client.get("/api/me").json()["user"] is None


def test_tampering_and_cancelling_are_refused(client):
    r = client.get("/api/auth/google/start", follow_redirects=False)
    client.nonce = parse_qs(urlsplit(r.headers["location"]).query)["nonce"][0]
    google_says(client)
    r = client.get("/api/auth/google/callback?code=abc&state=forged", follow_redirects=False)
    assert r.headers["location"] == "/account?google=failed"
    r = client.get("/api/auth/google/callback?error=access_denied", follow_redirects=False)
    assert r.headers["location"] == "/account?google=cancelled"
    client.cookies.clear()
    r = client.get("/api/auth/google/callback?code=abc&state=x", follow_redirects=False)
    assert r.headers["location"] == "/account?google=failed"
    assert client.get("/api/me").json()["user"] is None
    # A token for another app is refused even with the right state.
    assert go(client, aud="someone-else") == "failed"


def test_linking_and_unlinking(client):
    assert go(client, mode="link") == "signed_out"
    confirmed(client)
    outbox(client)
    assert go(client, mode="link", sub="555", email="ana.g@example.com") == "linked"
    assert client.get("/api/me/identities").json()["google"] == {"email": "ana.g@example.com"}
    assert any("Google" in m.subject for _, m in outbox(client))

    # Someone else can't take that Google account.
    client.post("/api/auth/logout")
    client.post("/api/auth/signup", json={"username": "Bo_42", "password": PW})
    assert go(client, mode="link", sub="555") == "taken"

    # Signing in with it reaches Ana's account.
    client.post("/api/auth/logout")
    assert go(client, sub="555") == "signed_in"
    assert client.get("/api/me").json()["user"]["username"] == "Ana_99"

    r = client.post("/api/me/google/remove", json={"password": "wrong"})
    assert r.status_code == 401
    r = client.post("/api/me/google/remove", json={"password": PW})
    assert r.json() == {"ok": True}
    assert client.get("/api/me/identities").json()["google"] is None


def test_an_account_without_a_password(client, monkeypatch):
    go(client, given_name="Cy")
    # Can't drop its only way in.
    r = client.post("/api/me/google/remove", json={"password": ""})
    assert r.status_code == 409 and r.json()["error"]["code"] == "needs_password"
    # Password sign-in never works for it.
    name = client.get("/api/me").json()["user"]["username"]
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"username": name, "password": ""})
    assert r.status_code in (401, 422)
    go(client, given_name="Cy")

    # A fresh sign-in stands in for the password; a stale one asks you to sign in again.
    later = time.time() + 16 * 60
    monkeypatch.setattr("app.accounts.time.time", lambda: later)
    r = client.post("/api/me/password", json={"password": "", "new_password": PW})
    assert r.status_code == 401 and r.json()["error"]["code"] == "reauth"
    monkeypatch.undo()
    r = client.post("/api/me/password", json={"password": "", "new_password": PW})
    assert r.status_code == 200, r.text
    assert client.get("/api/me").json()["user"]["has_password"] is True
    assert client.get("/api/me/identities").json()["has_password"] is True


def test_the_authenticator_still_applies_after_google(client):
    confirmed(client)
    assert go(client, mode="link", sub="555") == "linked"
    setup = client.post("/api/me/mfa/setup", json={"password": PW}).json()
    assert client.post("/api/me/mfa/enable", json={"code": now_code(setup["secret"])}).status_code == 200
    client.post("/api/auth/logout")

    r = client.get("/api/auth/google/start", follow_redirects=False)
    q = {k: v[0] for k, v in parse_qs(urlsplit(r.headers["location"]).query).items()}
    client.nonce = q["nonce"]
    google_says(client, sub="555")
    r = client.get(f"/api/auth/google/callback?code=abc&state={q['state']}", follow_redirects=False)
    assert r.headers["location"].startswith("/account/link#")
    assert client.get("/api/me").json()["user"] is None  # not signed in yet
    ticket = r.headers["location"].split("#", 1)[1]
    r = client.post("/api/auth/email-link/use", json={"token": ticket})
    assert r.json()["error"]["code"] == "mfa_required"
    r = client.post("/api/auth/email-link/use", json={"token": ticket, "code": now_code(setup["secret"], 1)})
    assert r.status_code == 200, r.text
