"""Account email over HTTP: confirming an address, signing in with it, reset links, notices about changes,
new-device alerts, signing out other devices, and the templates themselves."""

from __future__ import annotations

import re

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app import emails  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.test_api import settings  # noqa: E402
from tests.test_mfa_accounts import now_code  # noqa: E402

PW = "correct horse battery"


@pytest.fixture()
def app(tmp_path):
    a = create_app(settings(tmp_path, rate_auth_burst=1000, public_url="https://snazzlebop.test"))
    a.state.mailer.keep = True  # mail "on", kept in memory
    return a


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


def outbox(client) -> list[tuple[str, emails.Email]]:
    """Emails sent so far (and clears the list)."""
    mailer = client.app.state.mailer
    client.portal.call(mailer.drain)
    sent, mailer.sent = list(mailer.sent), []
    return sent


def link_token(email: emails.Email) -> str:
    found = re.search(r"https://snazzlebop\.test/account/(?:verify|reset)#([A-Za-z0-9_-]+)", email.text)
    assert found, email.text
    return found.group(1)


def signup(client, name="Ana_99", email="ana@example.com"):
    r = client.post("/api/auth/signup", json={"username": name, "password": PW, "email": email})
    assert r.status_code == 201, r.text
    return r.json()


def confirmed(client, name="Ana_99", email="ana@example.com"):
    signup(client, name, email)
    [(to, mail)] = outbox(client)
    assert to == email
    assert client.post("/api/auth/verify", json={"token": link_token(mail)}).json() == {"ok": True}


def test_sign_up_with_an_email_confirm_it_and_sign_in_with_it(client):
    body = signup(client, email="  Ana@Example.COM ")
    assert body["user"]["email"] == "ana@example.com" and body["user"]["email_verified"] is False
    [(to, mail)] = outbox(client)
    assert to == "ana@example.com" and mail.subject == "Confirm your email for Snazzlebop"
    client.post("/api/auth/logout")
    # Not confirmed yet: the address doesn't sign in.
    assert (
        client.post("/api/auth/login", json={"username": "ana@example.com", "password": PW}).status_code
        == 401
    )
    token = link_token(mail)
    assert client.post("/api/auth/verify", json={"token": token}).json() == {"ok": True}
    assert (
        client.post("/api/auth/verify", json={"token": token}).json()["error"]["code"] == "bad_link"
    )  # once
    r = client.post("/api/auth/login", json={"username": "ANA@example.com", "password": PW})
    assert r.status_code == 200 and r.json()["user"]["email_verified"] is True
    assert client.get("/api/me").json()["mail"] is True


def test_bad_emails_are_refused(client):
    for bad in ("nope", "a@b", "a b@c.com", "a@-x.com", "x" * 250 + "@a.com"):
        r = client.post("/api/auth/signup", json={"username": "Ana_99", "password": PW, "email": bad})
        assert r.status_code in (400, 422) and "bad_email" in r.text or r.status_code == 422, bad
    assert (
        client.post("/api/auth/signup", json={"username": "Ana_99", "password": PW, "email": ""}).status_code
        == 201
    )
    assert outbox(client) == []  # no email, nothing sent


def test_forgot_password_by_email(client):
    confirmed(client)
    first = client.cookies.get("sb_session")
    assert client.post("/api/auth/forgot", json={"login": "nobody_here"}).json() == {"ok": True}
    assert client.post("/api/auth/forgot", json={"login": "nobody@example.com"}).json() == {"ok": True}
    assert outbox(client) == []  # same answer, nothing sent
    assert client.post("/api/auth/forgot", json={"login": "Ana_99"}).json() == {"ok": True}
    assert client.post("/api/auth/forgot", json={"login": "ana@example.com"}).json() == {"ok": True}
    [(to, mail)] = outbox(client)  # one a minute per account
    assert to == "ana@example.com" and mail.subject == "Reset your Snazzlebop password"
    token = link_token(mail)

    r = client.post("/api/auth/reset", json={"token": token, "new_password": "short"})
    assert r.json()["error"]["code"] == "weak_password"  # the link survives a mistake
    r = client.post("/api/auth/reset", json={"token": token, "new_password": "a brand new phrase"})
    assert r.status_code == 200 and r.json()["user"]["username"] == "Ana_99"
    assert client.cookies.get("sb_session") != first
    r = client.post("/api/auth/reset", json={"token": token, "new_password": "another new phrase"})
    assert r.json()["error"]["code"] == "bad_link"
    [(_, notice)] = outbox(client)
    assert notice.subject == "Your Snazzlebop password was reset"
    client.post("/api/auth/logout")
    assert (
        client.post(
            "/api/auth/login", json={"username": "Ana_99", "password": "a brand new phrase"}
        ).status_code
        == 200
    )


def test_unconfirmed_emails_get_no_reset_links(client):
    signup(client)
    outbox(client)
    assert client.post("/api/auth/forgot", json={"login": "Ana_99"}).json() == {"ok": True}
    assert outbox(client) == []


def test_changing_and_removing_the_email(client):
    confirmed(client)
    r = client.post("/api/me/email", json={"email": "new@example.com", "password": "wrong password"})
    assert r.status_code == 401
    r = client.post("/api/me/email", json={"email": "new@example.com", "password": PW})
    assert r.status_code == 200 and r.json()["user"] == {
        "username": "Ana_99",
        "coins": 0,
        "powerups": {},
        "email": "new@example.com",
        "email_verified": False,
    }
    sent = dict((to, m.subject) for to, m in outbox(client))
    assert sent == {
        "ana@example.com": "Your Snazzlebop email was changed",
        "new@example.com": "Confirm your email for Snazzlebop",
    }
    assert client.post("/api/me/email/resend").json() == {"ok": True}
    [(_, again)] = outbox(client)
    assert client.post("/api/auth/verify", json={"token": link_token(again)}).json() == {"ok": True}
    assert client.post("/api/me/email/resend").json()["error"]["code"] == "already_confirmed"
    r = client.post("/api/me/email/remove", json={"password": PW})
    assert r.json()["user"]["email"] is None
    [(to, removed)] = outbox(client)
    assert to == "new@example.com" and removed.subject == "Your Snazzlebop email was removed"


def test_one_confirmed_email_per_account(client):
    signup(client, "Ana_99", "same@example.com")
    signup(client, "Bo_42", "same@example.com")  # Bo is signed in now
    mails = outbox(client)
    ana, bo = (link_token(m) for _, m in mails)
    assert client.post("/api/auth/verify", json={"token": bo}).json() == {"ok": True}
    assert client.post("/api/auth/verify", json={"token": ana}).json()["error"]["code"] == "email_taken"
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "Ana_99", "password": PW})
    r = client.post("/api/me/email", json={"email": "same@example.com", "password": PW})
    assert r.json()["error"]["code"] == "email_taken"


def test_a_new_device_and_security_changes_are_emailed(client):
    confirmed(client)
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "Ana_99", "password": PW})
    assert outbox(client) == []  # the browser it signed up on
    here = client.cookies.get("sb_session")
    client.cookies.clear()  # another browser: no session, no device cookie
    r = client.post(
        "/api/auth/login",
        json={"username": "Ana_99", "password": PW},
        headers={
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) AppleWebKit Version/18.0 Safari/604.1"
        },
    )
    assert r.status_code == 200
    [(_, alert)] = outbox(client)
    assert alert.subject == "New sign-in to your Snazzlebop account" and "Safari on iOS" in alert.text

    # Sign out other devices from the new browser: it stays in, the first one is out.
    assert client.post("/api/me/sessions/revoke").json() == {"ok": True}
    assert client.get("/api/me").json()["user"]["username"] == "Ana_99"
    client.cookies.set("sb_session", here)
    assert client.get("/api/me").json()["user"] is None
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"username": "Ana_99", "password": PW}).status_code == 200
    outbox(client)  # another new-device alert: this jar has no device cookie

    client.post("/api/me/password", json={"password": PW, "new_password": PW + "!"})
    [(_, changed)] = outbox(client)
    assert changed.subject == "Your Snazzlebop password was changed"
    r = client.post("/api/me/delete", json={"password": PW + "!"})
    assert r.status_code == 200, r.text
    [(_, bye)] = outbox(client)
    assert bye.subject == "Your Snazzlebop account was deleted"


def test_with_mail_off_the_email_options_say_so(tmp_path):
    with TestClient(create_app(settings(tmp_path, rate_auth_burst=1000))) as c:
        assert c.get("/api/me").json()["mail"] is False
        assert c.post("/api/auth/forgot", json={"login": "Ana_99"}).json()["error"]["code"] == "mail_off"
        signup(c)  # an email at sign-up is kept, just not confirmed
        assert c.get("/api/me").json()["user"]["email"] == "ana@example.com"
        r = c.post("/api/me/email", json={"email": "b@example.com", "password": PW})
        assert r.json()["error"]["code"] == "mail_off"


def test_templates_escape_everything_and_match_in_text():
    m = emails.Message(
        subject="Hi",
        preheader="<b>pre</b>",
        heading="Heading & more",
        paragraphs=['<script>alert("x")</script>'],
        button=("Go", 'https://snazzlebop.test/a?b=1&c="2"'),
        details=[("Device", "<img src=x>")],
    )
    e = emails.render(m, "https://snazzlebop.test")
    assert "<script>" not in e.html and "&lt;script&gt;" in e.html
    assert "<img src=x>" not in e.html and "c=&quot;2&quot;" in e.html
    assert '<script>alert("x")</script>' in e.text and 'Go: https://snazzlebop.test/a?b=1&c="2"' in e.text
    for build in (
        emails.verify_email("https://s.test", "Ana", "https://s.test/account/verify#t"),
        emails.reset_password("https://s.test", "Ana", "https://s.test/account/reset#t"),
        emails.new_device("https://s.test", "Ana", "Chrome on Windows"),
        emails.email_changed("https://s.test", "Ana", "new@example.com"),
        emails.goodbye("https://s.test", "Ana"),
    ):
        assert (
            build.subject and "Ana" in build.text and "https://" in build.html and "<script" not in build.html
        )
    assert emails.mask("new@example.com") == "n***@example.com"
    assert emails.describe_device("") == "a browser"


def link_from(mail: emails.Email) -> str:
    found = re.search(r"https://snazzlebop\.test/account/link#([A-Za-z0-9_-]+)", mail.text)
    assert found, mail.text
    return found.group(1)


def test_signing_in_with_an_emailed_link(client):
    confirmed(client)
    client.post("/api/auth/logout")
    for nobody in ("nobody@example.com", "not an email"):
        assert client.post("/api/auth/email-link", json={"email": nobody}).json() == {"ok": True}
    assert outbox(client) == []  # the same answer, and nothing sent
    assert client.post("/api/auth/email-link", json={"email": " ANA@example.com "}).json() == {"ok": True}
    assert client.post("/api/auth/email-link", json={"email": "ana@example.com"}).json() == {"ok": True}
    [(to, mail)] = outbox(client)  # one a minute per account
    assert to == "ana@example.com" and mail.subject == "Your Snazzlebop sign-in link"
    token = link_from(mail)
    r = client.post("/api/auth/email-link/use", json={"token": token})
    assert r.status_code == 200 and r.json()["user"]["username"] == "Ana_99"
    assert client.get("/api/me").json()["user"]["username"] == "Ana_99"
    client.post("/api/auth/logout")
    r = client.post("/api/auth/email-link/use", json={"token": token})
    assert r.json()["error"]["code"] == "bad_link"  # once only
    assert (
        client.post("/api/auth/email-link/use", json={"token": "x" * 30}).json()["error"]["code"]
        == "bad_link"
    )


def test_a_link_still_asks_for_the_authenticator(client):
    confirmed(client)
    secret = client.post("/api/me/mfa/setup", json={"password": PW}).json()["secret"]
    client.post("/api/me/mfa/enable", json={"code": now_code(secret)})
    outbox(client)
    client.post("/api/auth/logout")
    client.post("/api/auth/email-link", json={"email": "ana@example.com"})
    token = link_from(outbox(client)[0][1])
    r = client.post("/api/auth/email-link/use", json={"token": token})
    assert r.json()["error"]["code"] == "mfa_required"
    r = client.post("/api/auth/email-link/use", json={"token": token, "code": now_code(secret, ahead=1)})
    assert r.status_code == 200  # the link survived the missing code


def test_unconfirmed_emails_get_no_sign_in_link(client):
    signup(client)
    outbox(client)
    client.post("/api/auth/logout")
    assert client.post("/api/auth/email-link", json={"email": "ana@example.com"}).json() == {"ok": True}
    assert outbox(client) == []


def test_the_device_list_and_signing_out_one(client):
    signup(client, email="")
    ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) AppleWebKit Chrome/130.0 Safari/537.36"}
    here = client.cookies.get("sb_session")
    client.cookies.clear()
    client.post("/api/auth/login", json={"username": "Ana_99", "password": PW}, headers=ua)
    rows = client.get("/api/me/sessions").json()["sessions"]
    current = next(r for r in rows if r["current"])
    assert len(rows) == 2 and current["device"] == "Chrome on Windows"
    other = next(r for r in rows if not r["current"])
    assert len(other["id"]) == 12 and other["signed_in"] and other["last_seen"]
    assert client.post(f"/api/me/sessions/{other['id']}/revoke").json() == {"ok": True}
    assert len(client.get("/api/me/sessions").json()["sessions"]) == 1
    assert client.post(f"/api/me/sessions/{other['id']}/revoke").json()["error"]["code"] == "no_session"
    assert client.post("/api/me/sessions/nothex/revoke").json()["error"]["code"] == "bad_input"
    client.cookies.set("sb_session", here)
    assert client.get("/api/me").json()["user"] is None  # that browser is signed out
