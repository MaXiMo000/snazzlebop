"""The staff console: who gets in (named staff with an authenticator only), the queue (escalated club
cases and reports outside clubs), handing a case back, suspensions (sign-out everywhere, no sign-in,
lifting them), and the audit trail."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from tests.test_api import settings  # noqa: E402
from tests.test_mfa_accounts import now_code  # noqa: E402

PW = "correct horse battery"


@pytest.fixture()
def client(tmp_path):
    app = create_app(settings(tmp_path, rate_auth_burst=1000, staff_usernames=("staff_1", "staff_2")))
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


def make_staff(client, name="Staff_1"):
    be(client, name)
    secret = client.post("/api/me/mfa/setup", json={"password": PW}).json()["secret"]
    client.backup = client.post("/api/me/mfa/enable", json={"code": now_code(secret)}).json()["codes"]


def err(r) -> str:
    return r.json()["error"]["code"]


def test_only_named_staff_with_an_authenticator_get_in(client):
    be(client, "Ana_99")
    assert client.get("/api/me").json()["staff"] is False
    assert client.get("/api/staff/reports").status_code == 404  # doesn't announce itself
    be(client, "Staff_1")
    assert client.get("/api/me").json()["staff"] is True
    assert err(client.get("/api/staff/reports")) == "needs_mfa"
    make_staff(client)
    assert client.get("/api/staff/reports").json() == {"reports": [], "suspended": [], "actions": []}
    client.post("/api/auth/logout")
    assert client.get("/api/staff/reports").status_code == 404


def test_escalated_and_club_less_reports_reach_staff_and_can_go_back(client):
    make_staff(client)
    be(client, "Bo_42")
    be(client, "Ana_99")
    slug = client.post("/api/clubs", json={"name": "Hostel Four"}).json()["slug"]
    code = client.post(f"/api/clubs/{slug}/invites", json={}).json()["code"]
    for n in ("Bo_42", "Cy_77"):
        be(client, n)
        client.post("/api/clubs/join", json={"code": code})
    be(client, "Cy_77")
    client.post("/api/reports", json={"username": "Bo_42", "reason": "hate", "club": slug})
    client.post("/api/reports", json={"username": "Ana_99", "reason": "spam"})  # not about a club
    be(client, "Ana_99")
    [club_case] = client.get(f"/api/clubs/{slug}/reports").json()["reports"]
    client.post(f"/api/clubs/{slug}/reports/{club_case['id']}", json={"action": "escalate"})

    be(client, "Staff_1")
    rows = client.get("/api/staff/reports").json()["reports"]
    by_target = {r["target"]: r for r in rows}
    assert set(by_target) == {"Bo_42", "Ana_99"}
    assert by_target["Bo_42"]["status"] == "escalated" and by_target["Bo_42"]["club"] == "Hostel Four"
    assert by_target["Bo_42"]["can_return"] is True and by_target["Ana_99"]["can_return"] is False
    assert by_target["Ana_99"]["club"] is None and by_target["Ana_99"]["status"] == "open"
    assert client.post(
        f"/api/staff/reports/{by_target['Bo_42']['id']}", json={"action": "return"}
    ).json() == {"ok": True}
    assert [r["target"] for r in client.get("/api/staff/reports").json()["reports"]] == ["Ana_99"]
    assert client.post(
        f"/api/staff/reports/{by_target['Ana_99']['id']}", json={"action": "dismiss"}
    ).json() == {"ok": True}
    be(client, "Ana_99")  # back with the club's moderators, with the whole story
    [back] = client.get(f"/api/clubs/{slug}/reports").json()["reports"]
    assert back["status"] == "open" and back["can_act"] is True
    assert [h["text"] for h in back["history"]] == ["Reported", "Sent to staff", "Handed back to the club"]
    assert back["history"][-1]["actor"] == "Staff_1 (staff)"


def test_suspending_signs_out_blocks_sign_in_and_can_be_lifted(client):
    make_staff(client)
    be(client, "Bo_42")
    bo_cookie = client.cookies.get("sb_session")
    be(client, "Cy_77")
    client.post("/api/reports", json={"username": "Bo_42", "reason": "harassment", "note": "again and again"})
    be(client, "Staff_1")
    [case] = client.get("/api/staff/reports").json()["reports"]
    assert case["can_suspend"] is True and case["account"] == "Bo_42"
    act = f"/api/staff/reports/{case['id']}"
    assert err(client.post(act, json={"action": "suspend", "days": 3})) == "bad_input"
    body = {"action": "suspend", "days": 7, "reason": "Harassing people in rooms"}
    assert client.post(act, json=body).json() == {"ok": True}
    assert err(client.post(act, json={"action": "dismiss"})) == "handled"
    queue = client.get("/api/staff/reports").json()
    assert (
        queue["suspended"][0]["username"] == "Bo_42"
        and queue["suspended"][0]["reason"] == "Harassing people in rooms"
    )
    assert queue["actions"][0]["action"] == "suspend" and queue["actions"][0]["note"] == "7 d"
    last = queue["reports"][0]["history"][-1]
    assert last["text"] == "Account suspended for 7 days: Harassing people in rooms"
    assert last["actor"] == "Staff_1 (staff)"

    staff_cookie = client.cookies.get("sb_session")
    client.cookies.set("sb_session", bo_cookie)
    assert client.get("/api/me").json()["user"] is None  # signed out everywhere
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"username": "Bo_42", "password": PW})
    assert r.status_code == 403 and err(r) == "suspended"
    r = client.post("/api/auth/login", json={"username": "Bo_42", "password": "wrong password"})
    assert err(r) == "bad_login"  # the suspension is only told to the right password

    client.cookies.set("sb_session", staff_cookie)
    assert client.post("/api/staff/unsuspend", json={"username": "Bo_42"}).json() == {"ok": True}
    assert client.get("/api/staff/reports").json()["suspended"] == []
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"username": "Bo_42", "password": PW}).status_code == 200


def test_staff_can_not_be_suspended_and_guests_have_no_account(client):
    make_staff(client, "Staff_2")
    make_staff(client, "Staff_1")
    be(client, "Cy_77")
    client.post("/api/reports", json={"username": "Staff_2", "reason": "spam"})
    be(client, "Staff_1")
    [case] = client.get("/api/staff/reports").json()["reports"]
    assert case["can_suspend"] is False
    r = client.post(f"/api/staff/reports/{case['id']}", json={"action": "suspend", "days": 1})
    assert err(r) == "not_allowed"
    r = client.post(f"/api/staff/reports/{case['id']}", json={"action": "suspend", "days": 0})
    assert err(r) == "not_allowed"
    assert err(client.post("/api/staff/reports/999", json={"action": "dismiss"})) == "no_report"
