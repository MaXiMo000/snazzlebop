"""Clubs over HTTP: who can see a club, invite links (uses, expiry, bans), roles, handing over, leaving
and club rooms."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import update  # noqa: E402

from app.clubs import policy  # noqa: E402
from app.clubs.store import ClubStore  # noqa: E402
from app.db import ClubInvite  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.test_api import settings  # noqa: E402

PW = "correct horse battery"


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(settings(tmp_path, rate_auth_burst=1000))) as c:
        yield c


def be(client, name: str) -> None:
    """Sign in as `name`, making the account the first time."""
    client.post("/api/auth/logout")
    if client.post("/api/auth/login", json={"username": name, "password": PW}).status_code != 200:
        assert client.post("/api/auth/signup", json={"username": name, "password": PW}).status_code == 201


def new_club(client, owner="Ana_99", name="Hostel Four") -> str:
    be(client, owner)
    r = client.post("/api/clubs", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["slug"]


def invite(client, slug, **body) -> str:
    r = client.post(f"/api/clubs/{slug}/invites", json=body)
    assert r.status_code == 201, r.text
    return r.json()["code"]


def join(client, name, code):
    be(client, name)
    return client.post("/api/clubs/join", json={"code": code})


def err(r) -> str:
    return r.json()["error"]["code"]


def test_guests_and_outsiders_cant_see_a_club(client):
    slug = new_club(client)
    client.post("/api/auth/logout")
    assert client.get("/api/clubs").status_code == 401
    be(client, "Bo_42")
    assert client.get("/api/clubs").json() == {"clubs": []}
    assert client.get(f"/api/clubs/{slug}").status_code == 404
    assert client.get("/api/clubs/no-such-club").status_code == 404  # same answer: names can't be probed


def test_joining_by_invite_and_the_member_view(client):
    slug = new_club(client)
    code = invite(client, slug)
    r = join(client, "Bo_42", code.lower())  # typed by hand: case doesn't matter
    assert r.status_code == 200 and r.json()["role"] == "member"
    assert r.json()["invites"] == []  # members don't see invite links
    assert [m["username"] for m in r.json()["members"]] == ["Ana_99", "Bo_42"]
    assert client.get("/api/clubs").json()["clubs"][0]["members"] == 2
    assert join(client, "Bo_42", code).status_code == 200  # already in: fine, no use spent
    be(client, "Ana_99")
    assert client.get(f"/api/clubs/{slug}").json()["invites"][0]["uses_left"] == 24


def test_invites_run_out_expire_and_can_be_revoked(client):
    slug = new_club(client)
    once = invite(client, slug, uses=1)
    assert join(client, "Bo_42", once).status_code == 200
    assert err(join(client, "Cy_77", once)) == "bad_invite"

    be(client, "Ana_99")
    old = invite(client, slug)
    db = client.app.state.db

    async def expire() -> None:
        async with db.sessions() as s:
            await s.execute(update(ClubInvite).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
            await s.commit()

    client.portal.call(expire)
    assert err(join(client, "Cy_77", old)) == "bad_invite"

    be(client, "Ana_99")
    r = client.post(f"/api/clubs/{slug}/invites", json={})
    assert client.post(f"/api/clubs/{slug}/invites/{r.json()['id']}/revoke").json() == {"ok": True}
    assert err(join(client, "Cy_77", r.json()["code"])) == "bad_invite"
    assert err(join(client, "Cy_77", "NOTACODE22")) == "bad_invite"
    be(client, "Ana_99")
    for bad in ({"days": 0}, {"days": 31}, {"uses": 101}, {"uses": "5"}):
        assert client.post(f"/api/clubs/{slug}/invites", json=bad).status_code in (400, 422), bad


def test_roles_only_work_downwards(client):
    slug = new_club(client)
    code = invite(client, slug)
    for name in ("Bo_42", "Cy_77", "Di_55"):
        assert join(client, name, code).status_code == 200
    be(client, "Ana_99")
    assert client.post(f"/api/clubs/{slug}/members/Bo_42", json={"role": "admin"}).status_code == 200
    assert client.post(f"/api/clubs/{slug}/members/Cy_77", json={"role": "moderator"}).status_code == 200
    assert client.post(f"/api/clubs/{slug}/members/Ana_99", json={"role": "member"}).status_code == 403
    assert client.post(f"/api/clubs/{slug}/members/Di_55", json={"role": "owner"}).status_code == 403

    be(client, "Cy_77")  # a moderator: invites and removes members, nothing more
    assert client.post(f"/api/clubs/{slug}/invites", json={}).status_code == 201
    assert client.post(f"/api/clubs/{slug}/settings", json={"name": "Taken Over"}).status_code == 403
    assert client.post(f"/api/clubs/{slug}/members/Bo_42/remove", json={}).status_code == 403
    assert client.post(f"/api/clubs/{slug}/members/Di_55", json={"role": "moderator"}).status_code == 403

    be(client, "Bo_42")  # an admin: settings, moderators, but not other admins or the owner
    r = client.post(f"/api/clubs/{slug}/settings", json={"name": "Hostel 4", "rules": {"games": ["trivia"]}})
    assert (
        r.status_code == 200 and r.json()["name"] == "Hostel 4" and r.json()["rules"]["games"] == ["trivia"]
    )
    assert client.post(f"/api/clubs/{slug}/settings", json={"rules": {"games": ["nope"]}}).status_code == 400
    assert client.post(f"/api/clubs/{slug}/members/Di_55", json={"role": "admin"}).status_code == 403
    assert client.post(f"/api/clubs/{slug}/members/Ana_99/remove", json={}).status_code == 403
    assert client.post(f"/api/clubs/{slug}/members/Cy_77/remove", json={}).status_code == 200
    assert client.post(f"/api/clubs/{slug}/members/Nobody/remove", json={}).status_code == 404

    be(client, "Di_55")  # a member: none of it
    assert client.post(f"/api/clubs/{slug}/invites", json={}).status_code == 403
    assert client.post(f"/api/clubs/{slug}/delete").status_code == 403


def test_a_banned_member_cant_come_back(client):
    slug = new_club(client)
    code = invite(client, slug)
    assert join(client, "Bo_42", code).status_code == 200
    be(client, "Ana_99")
    assert client.post(f"/api/clubs/{slug}/members/Bo_42/remove", json={"ban": True}).status_code == 200
    r = join(client, "Bo_42", code)
    assert r.status_code == 403 and err(r) == "banned"
    assert client.get(f"/api/clubs/{slug}").status_code == 404
    assert client.get("/api/clubs").json() == {"clubs": []}


def test_handing_over_leaving_and_closing(client):
    slug = new_club(client)
    code = invite(client, slug)
    assert join(client, "Bo_42", code).status_code == 200
    be(client, "Ana_99")
    assert err(client.post(f"/api/clubs/{slug}/leave")) == "owner_leaving"
    assert client.post(f"/api/clubs/{slug}/transfer", json={"username": "Ana_99"}).status_code == 400
    assert client.post(f"/api/clubs/{slug}/transfer", json={"username": "Bo_42"}).status_code == 200
    roles = {m["username"]: m["role"] for m in client.get(f"/api/clubs/{slug}").json()["members"]}
    assert roles == {"Ana_99": "admin", "Bo_42": "owner"}
    assert client.post(f"/api/clubs/{slug}/leave").status_code == 200  # an admin now: leaves freely
    assert client.get(f"/api/clubs/{slug}").status_code == 404

    be(client, "Bo_42")  # the last one in: leaving closes the club
    assert client.post(f"/api/clubs/{slug}/leave").status_code == 200
    assert client.get(f"/api/clubs/{slug}").status_code == 404
    assert err(join(client, "Cy_77", code)) == "bad_invite"  # its invites went with it


def test_an_account_owns_a_handful_of_clubs(client):
    be(client, "Ana_99")
    for i in range(policy.MAX_OWNED):
        assert client.post("/api/clubs", json={"name": f"Club {i}"}).status_code == 201
    r = client.post("/api/clubs", json={"name": "One Too Many"})
    assert r.status_code == 409 and err(r) == "too_many_clubs"
    for bad in ({"name": "ab"}, {"name": "x" * 41}, {"name": "Fine", "rules": {"colour": "red"}}):
        assert client.post("/api/clubs", json=bad).status_code in (400, 422), bad


def test_club_rooms_show_on_the_club_page_only(client):
    slug = new_club(client)
    code = invite(client, slug)
    be(client, "Ana_99")
    r = client.post(f"/api/clubs/{slug}/rooms", json={"name": "Ana"})
    assert r.status_code == 201
    room, token = r.json()["code"], r.json()["token"]
    client.post("/api/rooms", json={"name": "Elsewhere"})  # an ordinary room isn't listed
    assert join(client, "Bo_42", code).json()["rooms"] == []  # nobody in it yet
    with client.websocket_connect(f"/ws/{room}") as ws:  # the host walks in
        ws.send_json({"t": "auth", "token": token})
        ws.receive_json()
        rows = client.get(f"/api/clubs/{slug}").json()["rooms"]
        assert [x["code"] for x in rows] == [room]
        assert rows[0] == {
            "code": room,
            "host": "Ana",
            "players": 1,
            "phase": "lobby",
            "game": None,
            "open": True,
        }
    assert client.post(f"/api/rooms/{room}/join", json={"name": "Bo"}).status_code == 200
    be(client, "Cy_77")
    assert client.post(f"/api/clubs/{slug}/rooms", json={"name": "Cy"}).status_code == 404


def test_changes_need_the_same_origin(client):
    slug = new_club(client)
    r = client.post(f"/api/clubs/{slug}/invites", json={}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_deleting_an_owner_account_passes_the_club_on(client):
    slug = new_club(client)
    code = invite(client, slug)
    for name in ("Bo_42", "Cy_77"):
        assert join(client, name, code).status_code == 200
    be(client, "Ana_99")
    assert client.post(f"/api/clubs/{slug}/members/Cy_77", json={"role": "moderator"}).status_code == 200
    lonely = client.post("/api/clubs", json={"name": "Just Me"}).json()["slug"]
    assert client.post("/api/me/delete", json={"password": PW}).status_code == 200
    be(client, "Cy_77")  # the moderator outranks the earlier-joined member
    r = client.get(f"/api/clubs/{slug}").json()
    assert r["role"] == "owner" and [m["username"] for m in r["members"]] == ["Bo_42", "Cy_77"]
    assert client.portal.call(client.app.state.db.user_by_name, "Ana_99") is None
    assert client.portal.call(ClubStore(client.app.state.db).by_slug, lonely) is None  # nobody left: closed


def test_club_rooms_follow_the_club_rules(client):
    be(client, "Ana_99")
    rules = {"games": ["imposter", "trivia"], "chat": False}
    slug = client.post("/api/clubs", json={"name": "Quiz Crew", "rules": rules}).json()["slug"]
    r = client.post(f"/api/clubs/{slug}/rooms", json={"name": "Ana"}).json()
    with client.websocket_connect(f"/ws/{r['code']}") as ws:
        ws.send_json({"t": "auth", "token": r["token"]})
        frame = ws.receive_json()
        assert sorted(g["id"] for g in frame["games"]) == ["imposter", "trivia"]
        assert frame["chat"]["muted"] is True
        ws.send_json({"t": "chat", "text": "hello"})
        assert ws.receive_json()["code"] == "muted"
        ws.send_json({"t": "start", "game": "price"})
        assert ws.receive_json()["code"] == "club_game"
    plain = client.post("/api/rooms", json={"name": "Ana"}).json()  # other rooms are untouched
    with client.websocket_connect(f"/ws/{plain['code']}") as ws:
        ws.send_json({"t": "auth", "token": plain["token"]})
        frame = ws.receive_json()
        assert len(frame["games"]) > 2 and frame["chat"]["muted"] is False


def test_owners_without_an_authenticator_are_nudged(client):
    slug = new_club(client)
    code = invite(client, slug)
    assert client.get(f"/api/clubs/{slug}").json()["secure_nudge"] is True
    assert join(client, "Bo_42", code).json()["secure_nudge"] is False  # members aren't
