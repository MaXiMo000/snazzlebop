"""Safety over HTTP: blocking (friends, invites, presence, joining rooms, chat), reporting with server-side
context, the club moderators' queue (dismiss, mute, remove, ban, escalate, the audit log), downloading
your data, and the privacy contact."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from app.rooms import HubError  # noqa: E402
from tests.test_api import settings  # noqa: E402

PW = "correct horse battery"


@pytest.fixture()
def client(tmp_path):
    with TestClient(
        create_app(settings(tmp_path, rate_auth_burst=1000, privacy_contact="privacy@example.com"))
    ) as c:
        yield c


def be(client, name):
    client.post("/api/auth/logout")
    if client.post("/api/auth/login", json={"username": name, "password": PW}).status_code != 200:
        assert client.post("/api/auth/signup", json={"username": name, "password": PW}).status_code == 201


def err(r) -> str:
    return r.json()["error"]["code"]


def club_with(client, names, roles=None):
    be(client, names[0])
    slug = client.post("/api/clubs", json={"name": "Hostel Four"}).json()["slug"]
    code = client.post(f"/api/clubs/{slug}/invites", json={}).json()["code"]
    for n in names[1:]:
        be(client, n)
        client.post("/api/clubs/join", json={"code": code})
    be(client, names[0])
    for n, role in (roles or {}).items():
        client.post(f"/api/clubs/{slug}/members/{n}", json={"role": role})
    return slug


def friends(client, a, b):
    be(client, b)
    be(client, a)
    client.post("/api/friends", json={"username": b})
    be(client, b)
    client.post("/api/friends", json={"username": a})


def test_blocking_ends_friendship_presence_and_invites(client):
    slug = club_with(client, ["Ana_99", "Bo_42"])
    friends(client, "Ana_99", "Bo_42")
    be(client, "Bo_42")
    client.get("/api/notifications")  # Bo is online
    be(client, "Ana_99")
    assert client.post("/api/blocks", json={"username": "Bo_42"}).json() == {"ok": True}
    assert [p["username"] for p in client.get("/api/blocks").json()["people"]] == ["Bo_42"]
    assert client.get("/api/friends").json()["friends"] == []
    members = {m["username"]: m["status"] for m in client.get(f"/api/clubs/{slug}").json()["members"]}
    assert members["Bo_42"] == "offline"  # online, but blocked: looks offline
    room = client.post(f"/api/clubs/{slug}/rooms", json={"name": "Ana"}).json()["code"]
    assert client.get(f"/api/rooms/{room}/invitees").json()["people"] == []
    assert err(client.post(f"/api/rooms/{room}/invite", json={"username": "Bo_42"})) == "cant_invite"

    be(client, "Bo_42")  # the blocked side: can't add Ana back, can't walk into her room
    assert err(client.post("/api/friends", json={"username": "Ana_99"})) == "cant_add"
    assert err(client.post(f"/api/rooms/{room}/join", json={"name": "Bo"})) == "cant_join"

    be(client, "Ana_99")
    assert client.post("/api/blocks/remove", json={"username": "Bo_42"}).json() == {"ok": True}
    assert client.get("/api/blocks").json()["people"] == []
    be(client, "Bo_42")
    assert client.post(f"/api/rooms/{room}/join", json={"name": "Bo"}).status_code == 200


def test_blocking_in_a_room_hides_chat_both_ways(client):
    be(client, "Bo_42")
    be(client, "Ana_99")
    r = client.post("/api/rooms", json={"name": "Ana"}).json()
    code, ana_pid = r["code"], r["player_id"]
    be(client, "Bo_42")
    bo_pid = client.post(f"/api/rooms/{code}/join", json={"name": "Bo"}).json()["player_id"]
    hub = client.app.state.hub
    room = hub.get(code)
    hub._chat(room, bo_pid, {"text": "hello all"})
    assert [m["text"] for m in hub._chat_view(room, ana_pid)["messages"]] == ["hello all"]

    be(client, "Ana_99")
    assert client.post(f"/api/rooms/{code}/block", json={"player_id": bo_pid}).json() == {"ok": True}
    room.chat_last.clear()
    hub._chat(room, ana_pid, {"text": "from ana"})
    assert hub._chat_view(room, ana_pid)["messages"][-1]["text"] == "from ana"
    assert [m["text"] for m in hub._chat_view(room, ana_pid)["messages"]] == ["from ana"]  # Bo's are gone
    assert [m["text"] for m in hub._chat_view(room, bo_pid)["messages"]] == ["hello all"]  # and Ana's to Bo
    client.cookies.clear()  # a guest: no account
    guest = client.post(f"/api/rooms/{code}/join", json={"name": "Guest"})
    be(client, "Ana_99")
    r = client.post(f"/api/rooms/{code}/block", json={"player_id": guest.json()["player_id"]})
    assert err(r) == "no_account"


def test_reports_carry_server_side_context_to_the_club_moderators(client):
    slug = club_with(client, ["Ana_99", "Bo_42", "Cy_77", "Di_55"], roles={"Cy_77": "moderator"})
    be(client, "Ana_99")
    r = client.post(f"/api/clubs/{slug}/rooms", json={"name": "Ana"}).json()
    code = r["code"]
    be(client, "Bo_42")
    bo_pid = client.post(f"/api/rooms/{code}/join", json={"name": "Bo"}).json()["player_id"]
    hub = client.app.state.hub
    hub._chat(hub.get(code), bo_pid, {"text": "something nasty"})

    be(client, "Di_55")  # not in the room: can't report from it
    assert (
        err(client.post(f"/api/rooms/{code}/report", json={"player_id": bo_pid, "reason": "hate"}))
        == "not_in_room"
    )
    client.post(f"/api/rooms/{code}/join", json={"name": "Di"})
    body = {"player_id": bo_pid, "reason": "hate", "note": "not ok \x00 at all"}
    assert client.post(f"/api/rooms/{code}/report", json=body).json() == {"ok": True}
    again = {**body, "note": "and again"}
    assert client.post(f"/api/rooms/{code}/report", json=again).json() == {
        "ok": True
    }  # added to the open one
    assert err(client.post(f"/api/rooms/{code}/report", json={**body, "reason": "nope"})) == "bad_input"
    assert err(client.get(f"/api/clubs/{slug}/reports")) == "not_allowed"  # members don't see the queue

    assert client.get(f"/api/clubs/{slug}").json()["open_reports"] == 0  # not shown to members
    be(client, "Cy_77")  # a moderator
    assert client.get(f"/api/clubs/{slug}").json()["open_reports"] == 1
    queue = client.get(f"/api/clubs/{slug}/reports").json()
    [rep] = queue["reports"]
    assert (
        rep["target"] == "Bo"
        and rep["reason"] == "Hate or slurs"
        and rep["note"] == "not ok at all / and again"
    )
    assert rep["context"] == [{"name": "Bo", "text": "something nasty"}] and rep["room"] == code
    assert rep["can_act"] is True and rep["status"] == "open"

    act = f"/api/clubs/{slug}/reports/{rep['id']}"
    assert err(client.post(act, json={"action": "mute", "hours": 5})) == "bad_input"
    assert client.post(act, json={"action": "mute", "hours": 24}).json() == {"ok": True}
    with pytest.raises(HubError) as raised:
        hub._chat(hub.get(code), bo_pid, {"text": "again"})
    assert raised.value.code == "muted"
    assert hub._chat_view(hub.get(code), bo_pid)["muted"] is True
    queue = client.get(f"/api/clubs/{slug}/reports").json()
    assert queue["reports"][0]["status"] == "actioned" and queue["muted"][0]["username"] == "Bo_42"
    assert queue["actions"][0] == {
        "actor": "Cy_77",
        "target": "Bo",
        "action": "mute",
        "note": "24 h",
        "at": queue["actions"][0]["at"],
    }
    assert err(client.post(act, json={"action": "ban"})) == "handled"
    assert client.post(f"/api/clubs/{slug}/unmute", json={"username": "Bo_42"}).json() == {"ok": True}
    hub.get(code).chat_last.clear()
    hub._chat(hub.get(code), bo_pid, {"text": "sorry"})  # unmuted


def test_moderators_act_only_below_their_role_and_can_escalate(client):
    slug = club_with(client, ["Ana_99", "Bo_42", "Cy_77"], roles={"Cy_77": "moderator", "Bo_42": "admin"})
    be(client, "Ana_99")
    assert client.post("/api/reports", json={"username": "Bo_42", "reason": "spam", "club": slug}).json() == {
        "ok": True
    }
    assert err(client.post("/api/reports", json={"username": "Ana_99", "reason": "spam"})) == "bad_target"
    assert (
        err(client.post("/api/reports", json={"username": "Bo_42", "reason": "spam", "club": "nope"}))
        == "no_club"
    )
    be(client, "Cy_77")
    [rep] = client.get(f"/api/clubs/{slug}/reports").json()["reports"]
    assert rep["can_act"] is False  # an admin is above a moderator
    act = f"/api/clubs/{slug}/reports/{rep['id']}"
    assert err(client.post(act, json={"action": "ban"})) == "not_allowed"
    assert client.post(act, json={"action": "escalate"}).json() == {"ok": True}
    assert client.get(f"/api/clubs/{slug}/reports").json()["reports"][0]["status"] == "escalated"

    be(client, "Cy_77")
    client.post("/api/reports", json={"username": "Ana_99", "reason": "other", "club": slug})
    be(client, "Ana_99")  # the owner removes... no: it's about her. She can't act on herself
    rows = client.get(f"/api/clubs/{slug}/reports").json()["reports"]
    about_her = next(r for r in rows if r["target"] == "Ana_99")
    assert about_her["can_act"] is False


def test_removing_and_banning_from_the_queue(client):
    slug = club_with(client, ["Ana_99", "Bo_42", "Cy_77"])
    be(client, "Cy_77")
    client.post("/api/reports", json={"username": "Bo_42", "reason": "cheating", "club": slug})
    be(client, "Ana_99")
    [rep] = client.get(f"/api/clubs/{slug}/reports").json()["reports"]
    assert client.post(f"/api/clubs/{slug}/reports/{rep['id']}", json={"action": "ban"}).json() == {
        "ok": True
    }
    names = [m["username"] for m in client.get(f"/api/clubs/{slug}").json()["members"]]
    assert "Bo_42" not in names
    actions = client.get(f"/api/clubs/{slug}/reports").json()["actions"]
    assert [a["action"] for a in actions] == ["ban"]


def test_too_many_reports_in_a_day(client):
    for n in range(21):
        be(client, f"Target_{n}")
    be(client, "Ana_99")
    for n in range(20):
        assert client.post("/api/reports", json={"username": f"Target_{n}", "reason": "spam"}).json() == {
            "ok": True
        }
    assert (
        err(client.post("/api/reports", json={"username": "Target_20", "reason": "spam"}))
        == "too_many_reports"
    )


def test_download_my_data_and_the_privacy_contact(client):
    assert client.get("/api/site").json() == {"privacy_contact": "privacy@example.com"}
    be(client, "Bo_42")
    be(client, "Ana_99")
    client.post("/api/blocks", json={"username": "Bo_42"})
    r = client.get("/api/me/export")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert data["account"]["username"] == "Ana_99" and data["blocked"] == ["Bo_42"]
    assert set(data) >= {"exported_at", "account", "games", "clubs", "friends", "notifications", "settings"}
    client.post("/api/auth/logout")
    assert client.get("/api/me/export").status_code == 401


def test_a_closed_club_takes_its_reports_with_it(client):
    slug = club_with(client, ["Ana_99", "Bo_42", "Cy_77"])
    be(client, "Cy_77")
    assert client.post("/api/reports", json={"username": "Bo_42", "reason": "spam", "club": slug}).json() == {
        "ok": True
    }
    be(client, "Ana_99")
    client.post(f"/api/clubs/{slug}/delete")
    again = club_with(client, ["Ana_99", "Bo_42", "Cy_77"])  # SQLite may hand out the same id
    assert client.get(f"/api/clubs/{again}/reports").json()["reports"] == []
    be(client, "Cy_77")  # and the same report in the new club isn't a duplicate
    assert client.post(
        "/api/reports", json={"username": "Bo_42", "reason": "spam", "club": again}
    ).json() == {"ok": True}
