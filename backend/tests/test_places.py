"""Places: the address rules, staff adding places, verifying with an emailed code (tries, one address per
account), alumni after a year, requests for unknown domains, and clubs that require a place."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import update  # noqa: E402

from app import places  # noqa: E402
from app.db import UserPlace  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.test_api import settings  # noqa: E402
from tests.test_mfa_accounts import now_code  # noqa: E402

PW = "correct horse battery"


@pytest.fixture()
def client(tmp_path):
    app = create_app(settings(tmp_path, rate_auth_burst=1000, staff_usernames=("staff_1",)))
    app.state.mailer.keep = True
    with TestClient(app) as c:
        c.backup = []
        yield c


def be(client, name):
    client.post("/api/auth/logout")
    body = {"username": name, "password": PW}
    r = client.post("/api/auth/login", json=body)
    if r.status_code == 401 and r.json()["error"]["code"] == "mfa_required":
        r = client.post("/api/auth/login", json=body | {"code": client.backup.pop()})
    if r.status_code != 200:
        assert client.post("/api/auth/signup", json=body).status_code == 201


def err(r) -> str:
    return r.json()["error"]["code"]


def add_place(client, name="IIT Delhi", domains=("iitd.ac.in",), kind="college"):
    be(client, "Staff_1")
    if not client.backup:
        secret = client.post("/api/me/mfa/setup", json={"password": PW}).json()["secret"]
        client.backup = client.post("/api/me/mfa/enable", json={"code": now_code(secret)}).json()["codes"]
    r = client.post("/api/staff/places", json={"name": name, "kind": kind, "domains": list(domains)})
    assert r.status_code == 200, r.text
    return next(p for p in r.json()["places"] if p["name"] == name)


def last_code(client) -> tuple[str, str]:
    mailer = client.app.state.mailer
    client.portal.call(mailer.drain)
    to, mail = mailer.sent[-1]
    return to, re.search(r"\b(\d{6})\b", mail.text).group(1)


def verify(client, name, email):
    be(client, name)
    r = client.post("/api/me/places/start", json={"email": email})
    assert r.status_code == 200, r.text
    _, code = last_code(client)
    return client.post("/api/me/places/confirm", json={"code": code})


def test_address_rules():
    assert places.is_free("gmail.com") and places.is_free("yahoo.co.in") and places.is_free("outlook.fr")
    assert not places.is_free("iitd.ac.in") and not places.is_free("acme.com")
    assert places.clean_domain(" @IITD.ac.in ") == "iitd.ac.in"
    for bad in ("gmail.com", "nodot", "-x.com", "a..b", "x" * 130 + ".com"):
        with pytest.raises(ValueError):
            places.clean_domain(bad)
    now = datetime.now(UTC)
    assert places.standing(now + timedelta(days=1), now) == "verified"
    assert places.standing(now - timedelta(days=1), now) == "alumni"


def test_verifying_a_place_with_an_emailed_code(client):
    place = add_place(client, domains=("iitd.ac.in", "iitd.ernet.in"))
    assert place["domains"] == ["iitd.ac.in", "iitd.ernet.in"] and place["members"] == 0
    be(client, "Ana_99")
    assert err(client.post("/api/me/places/start", json={"email": "ana@gmail.com"})) == "free_email"
    r = client.post("/api/me/places/start", json={"email": "ana@cs.iitd.ac.in"})  # a subdomain counts
    assert r.json() == {
        "place": {"slug": place["slug"], "name": "IIT Delhi"},
        "sent_to": "a***@cs.iitd.ac.in",
    }
    to, code = last_code(client)
    assert to == "ana@cs.iitd.ac.in"
    assert err(client.post("/api/me/places/start", json={"email": "ana@cs.iitd.ac.in"})) == "slow_down"
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"
    assert err(client.post("/api/me/places/confirm", json={"code": wrong})) == "bad_code"
    r = client.post("/api/me/places/confirm", json={"code": f"{code[:3]} {code[3:]}"})  # spaces are fine
    [mine] = r.json()["places"]
    assert mine["name"] == "IIT Delhi" and mine["status"] == "verified" and mine["kind"] == "college"
    assert err(client.post("/api/me/places/confirm", json={"code": code})) == "no_code"  # used up
    # The same address can't verify a second account.
    be(client, "Bo_42")
    assert err(client.post("/api/me/places/start", json={"email": "ANA@cs.iitd.ac.in"})) == "email_used"
    be(client, "Staff_1")
    assert client.get("/api/staff/places").json()["places"][0]["members"] == 1


def test_five_wrong_codes_and_the_code_is_gone(client):
    add_place(client)
    be(client, "Ana_99")
    client.post("/api/me/places/start", json={"email": "ana@iitd.ac.in"})
    _, code = last_code(client)
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"
    for _ in range(5):
        assert err(client.post("/api/me/places/confirm", json={"code": wrong})) == "bad_code"
    assert err(client.post("/api/me/places/confirm", json={"code": code})) == "too_many_tries"


def test_unknown_domains_become_requests_staff_can_add_or_decline(client):
    be(client, "Ana_99")
    for _ in range(2):
        r = client.post("/api/me/places/start", json={"email": "ana@acme-labs.com"})
        assert err(r) == "unknown_place" and "acme-labs.com" in r.json()["error"]["message"]
    be(client, "Bo_42")
    client.post("/api/me/places/start", json={"email": "bo@other.org"})
    add_place(client, "IIT Delhi")
    reqs = {r["domain"]: r["count"] for r in client.get("/api/staff/places").json()["requests"]}
    assert reqs == {"acme-labs.com": 2, "other.org": 1}
    r = client.post(
        "/api/staff/places", json={"name": "Acme Labs", "kind": "company", "domains": ["acme-labs.com"]}
    )
    assert [q["domain"] for q in r.json()["requests"]] == ["other.org"]  # added: no longer a request
    r = client.post("/api/staff/places/requests/decline", json={"domain": "other.org"})
    assert r.json()["requests"] == []
    # Domains belong to one place; free providers never do; names are unique.
    r = client.post("/api/staff/places", json={"name": "Copy", "kind": "college", "domains": ["iitd.ac.in"]})
    assert err(r) == "domain_taken"
    r = client.post("/api/staff/places", json={"name": "Mail", "kind": "college", "domains": ["gmail.com"]})
    assert err(r) == "bad_input"
    r = client.post("/api/staff/places", json={"name": "IIT Delhi", "kind": "college", "domains": ["x.edu"]})
    assert err(r) == "place_exists"
    be(client, "Ana_99")  # not staff
    assert client.get("/api/staff/places").status_code == 404


def test_after_a_year_it_shows_as_alumni_and_can_be_removed(client):
    place = add_place(client)
    verify(client, "Ana_99", "ana@iitd.ac.in")

    async def a_year_on() -> None:
        async with client.app.state.db.sessions() as s:
            await s.execute(update(UserPlace).values(expires_at=datetime.now(UTC) - timedelta(days=1)))
            await s.commit()

    client.portal.call(a_year_on)
    [mine] = client.get("/api/me/places").json()["places"]
    assert mine["status"] == "alumni"
    r = client.post(f"/api/me/places/{place['slug']}/remove")
    assert r.json()["places"] == []


def test_a_club_for_one_place(client):
    place = add_place(client)
    verify(client, "Cy_77", "cy@iitd.ac.in")
    be(client, "Ana_99")
    r = client.post("/api/clubs", json={"name": "Hostel Four", "rules": {"place": "nowhere"}})
    assert err(r) == "bad_input"
    slug = client.post("/api/clubs", json={"name": "Hostel Four", "rules": {"place": place["slug"]}}).json()[
        "slug"
    ]
    code = client.post(f"/api/clubs/{slug}/invites", json={}).json()["code"]
    be(client, "Bo_42")  # not verified there
    r = client.post("/api/clubs/join", json={"code": code})
    assert err(r) == "place_required" and "IIT Delhi" in r.json()["error"]["message"]
    be(client, "Cy_77")
    detail = client.post("/api/clubs/join", json={"code": code}).json()
    assert detail["place"] == {"slug": place["slug"], "name": "IIT Delhi"}
    assert detail["rules"]["place"] == place["slug"]
    badges = {m["username"]: m["places"] for m in detail["members"]}
    assert badges == {"Ana_99": [], "Cy_77": ["IIT Delhi"]}
