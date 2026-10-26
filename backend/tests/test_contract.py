"""The HTTP contract: every API route is called for real and each response body is validated against
the model its route declares (app/schemas.py, strict: an undeclared field fails), errors against
ErrorBody. A route nobody calls here fails too, so a new route can't skip the contract."""

from __future__ import annotations

import re
import time
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import TypeAdapter  # noqa: E402

from app import coins, mfa, schemas, webpush  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.test_api import settings  # noqa: E402

PW = "correct horse battery"


@pytest.fixture()
def client(tmp_path):
    app = create_app(
        settings(tmp_path, rate_auth_burst=1000, integration_token="i" * 40, staff_usernames=("ana_99",))
    )
    app.state.mailer.keep = True  # mail on (kept in memory), so the email routes answer for real
    with TestClient(app) as c:
        yield c


def api_routes(routes: list[Any]) -> list[APIRoute]:
    """Every APIRoute, including those inside included routers (wrapped in newer FastAPI versions)."""
    out: list[APIRoute] = []
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            out += api_routes(inner.routes)
        elif isinstance(route, APIRoute):
            out.append(route)
    return out


class Contract:
    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.models = {
            (method, route.path): route.response_model
            for route in api_routes(client.app.routes)
            if route.path.startswith("/api/")
            for method in route.methods
        }
        self.called: set[tuple[str, str]] = set()

    def call(self, method: str, path: str, template: str | None = None, **kw: Any) -> Any:
        r = self.client.request(method, path, **kw)
        key = (method, template or path)
        assert key in self.models, f"{key} is not a declared API route"
        self.called.add(key)
        body = r.json()
        if r.status_code >= 400:
            schemas.ErrorBody.model_validate(body)
        else:
            TypeAdapter(self.models[key]).validate_python(body, strict=False)
        return body

    def redirect(self, path: str) -> str:
        """A browser-navigation route: answers with a redirect, not JSON."""
        r = self.client.get(path, follow_redirects=False)
        assert r.status_code == 303, r.text
        self.called.add(("GET", path.split("?")[0]))
        return r.headers["location"]


def test_every_route_matches_its_declared_model(client):
    c = Contract(client)
    games = c.call("GET", "/api/games")
    assert {g["id"] for g in games} >= {"trivia", "imposter"}
    c.call("GET", "/api/stats")

    room = c.call("POST", "/api/rooms", json={"name": "Host"})
    code = room["code"]
    c.call("POST", f"/api/rooms/{code}/join", "/api/rooms/{code}/join", json={"name": "Guest"})
    c.call("POST", f"/api/rooms/{code}/tv", "/api/rooms/{code}/tv")
    c.call("POST", f"/api/rooms/{code}/audience", "/api/rooms/{code}/audience", json={"name": "Fan"})
    c.call("POST", "/api/rooms/ZZZZZ/join", "/api/rooms/{code}/join", json={"name": "Lost"})  # an error body

    assert c.call("GET", "/api/me")["user"] is None
    c.call("GET", "/api/me/stats")  # 401 for a guest: the error body
    made = c.call("POST", "/api/auth/signup", json={"username": "Ana_99", "password": PW})
    c.call("POST", "/api/auth/signup", json={"username": "Ana_99", "password": PW})  # taken: error
    c.call("GET", "/api/me")
    db = client.app.state.db
    user = client.portal.call(db.user_by_name, "Ana_99")
    rows = [{"user_id": user.id, "game_id": "trivia", "place": 1, "players": 4, "points": 300, "coins": 50}]
    client.portal.call(db.record_results, rows, coins.season_of(), coins.DAILY_COIN_CAP)
    c.call("GET", "/api/me/stats")
    c.call("GET", "/api/shop")
    c.call("POST", "/api/shop/buy", json={"item": "peek"})
    c.call("GET", "/api/leaderboard")

    c.call("POST", "/api/auth/signup", json={"username": "Bo_42", "password": PW})
    c.call("POST", "/api/friends", json={"username": "Ana_99"})
    c.call("POST", "/api/auth/logout")
    c.call("POST", "/api/auth/login", json={"username": "Ana_99", "password": PW})
    c.call("POST", "/api/friends", json={"username": "Bo_42"})
    friends = c.call("GET", "/api/friends")
    assert friends["friends"] and friends["friends"][0]["username"] == "Bo_42"
    c.call("POST", "/api/friends/remove", json={"username": "Bo_42"})

    c.call("POST", "/api/clubs", json={"name": "x"})  # too short: the error body
    slug = c.call("POST", "/api/clubs", json={"name": "Hostel Four", "about": "Quiz nights"})["slug"]
    c.call("GET", "/api/clubs")
    club = "/api/clubs/{slug}"
    c.call("GET", f"/api/clubs/{slug}", club)
    c.call("GET", f"/api/clubs/{slug}/boards", club + "/boards")
    c.call(
        "POST", f"/api/clubs/{slug}/challenge/claim", club + "/challenge/claim"
    )  # not reached: an error body
    c.call("POST", f"/api/clubs/{slug}/settings", club + "/settings", json={"rules": {"chat": False}})
    invite = c.call("POST", f"/api/clubs/{slug}/invites", club + "/invites", json={"uses": 5})
    spare = c.call("POST", f"/api/clubs/{slug}/invites", club + "/invites", json={})
    c.call("POST", f"/api/clubs/{slug}/invites/{spare['id']}/revoke", club + "/invites/{invite_id}/revoke")
    seat = c.call("POST", f"/api/clubs/{slug}/rooms", club + "/rooms", json={"name": "Ana"})
    c.call(
        "POST",
        f"/api/clubs/{slug}/battles",
        club + "/battles",
        json={"name": "Ana", "kind": "group", "game": "imposter"},
    )
    room_code = seat["code"]
    me_in_room = {"player_id": seat["player_id"]}
    c.call(
        "POST",
        f"/api/rooms/{room_code}/report",
        "/api/rooms/{code}/report",
        json={**me_in_room, "reason": "spam"},
    )
    c.call(
        "POST", f"/api/rooms/{room_code}/block", "/api/rooms/{code}/block", json=me_in_room
    )  # yourself: error
    c.call("POST", "/api/reports", json={"username": "Bo_42", "reason": "spam"})
    c.call("GET", f"/api/clubs/{slug}/reports", club + "/reports")
    c.call(
        "POST", f"/api/clubs/{slug}/reports/999", club + "/reports/{report_id}", json={"action": "dismiss"}
    )
    c.call("POST", f"/api/clubs/{slug}/unmute", club + "/unmute", json={"username": "Bo_42"})
    c.call("POST", "/api/blocks", json={"username": "Bo_42"})
    c.call("GET", "/api/blocks")
    c.call("POST", "/api/blocks/remove", json={"username": "Bo_42"})
    auth = {"Authorization": "Bearer " + "i" * 40}
    cases = c.call("GET", "/api/integrations/reports", headers=auth)["reports"]
    one = "/api/integrations/reports/{public_id}"
    pid = cases[0]["id"]
    c.call("GET", f"/api/integrations/reports/{pid}", one, headers=auth)
    triage = {"source": "ai-triage", "triage": {"label": "spam", "score": 0.5, "summary": "Looks like spam"}}
    c.call("POST", f"/api/integrations/reports/{pid}", one, json=triage, headers=auth)
    c.call("GET", "/api/integrations/health", headers=auth)
    c.call("GET", "/api/me/export")
    c.call("GET", "/api/site")
    c.call("GET", f"/api/rooms/{room_code}/invitees", "/api/rooms/{code}/invitees")
    c.call("POST", f"/api/rooms/{room_code}/invite", "/api/rooms/{code}/invite", json={"username": "Bo_42"})
    c.call("POST", f"/api/clubs/{slug}/up", club + "/up", json={"game": "trivia", "minutes": 30})
    c.call("POST", f"/api/clubs/{slug}/up/go", club + "/up/go", json={"name": "Ana"})  # no match yet: error
    c.call("POST", f"/api/clubs/{slug}/up/cancel", club + "/up/cancel")
    c.call("POST", f"/api/clubs/{slug}/mute", club + "/mute", json={"muted": True})
    c.call("GET", "/api/notifications")
    c.call("POST", "/api/notifications/read", json={})
    c.call("GET", "/api/me/notify")
    c.call("POST", "/api/me/notify", json={"quiet": {"from": "23:00", "to": "08:00"}, "tz": 60})
    point = webpush.b64u(webpush._point(ec.generate_private_key(ec.SECP256R1()).public_key()))
    sub = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/x",
        "p256dh": point,
        "auth": webpush.b64u(b"0" * 16),
    }
    c.call("POST", "/api/push/subscribe", json=sub)
    c.call("POST", "/api/push/unsubscribe", json={"endpoint": sub["endpoint"]})
    c.call("POST", "/api/auth/logout")
    c.call("POST", "/api/auth/login", json={"username": "Bo_42", "password": PW})
    c.call("POST", "/api/clubs/join", json={"code": invite["code"]})
    c.call("POST", f"/api/clubs/{slug}/leave", club + "/leave")
    c.call("POST", "/api/clubs/join", json={"code": invite["code"]})
    c.call("POST", "/api/auth/logout")
    c.call("POST", "/api/auth/login", json={"username": "Ana_99", "password": PW})
    member = club + "/members/{username}"
    c.call("POST", f"/api/clubs/{slug}/members/Bo_42", member, json={"role": "admin"})
    c.call("POST", f"/api/clubs/{slug}/transfer", club + "/transfer", json={"username": "Bo_42"})
    c.call("POST", f"/api/clubs/{slug}/members/Bo_42/remove", member + "/remove", json={})  # error
    c.call("POST", f"/api/clubs/{slug}/delete", club + "/delete")  # not the owner now: error
    second = c.call("POST", "/api/clubs", json={"name": "Night Owls"})["slug"]
    c.call("POST", f"/api/clubs/{second}/delete", club + "/delete")

    c.call("GET", "/api/me/mfa")
    setup = c.call("POST", "/api/me/mfa/setup", json={"password": PW})
    c.call("POST", "/api/me/mfa/enable", json={"code": "000000"})  # wrong: the error body
    code = mfa.totp_at(setup["secret"], int(time.time()) // mfa.TOTP_STEP)
    backup = c.call("POST", "/api/me/mfa/enable", json={"code": code})["codes"]
    c.call("GET", "/api/staff/reports")  # staff, with the authenticator on
    c.call("POST", "/api/staff/reports/999", "/api/staff/reports/{report_id}", json={"action": "dismiss"})
    c.call("POST", "/api/staff/unsuspend", json={"username": "Bo_42"})
    c.call("GET", "/api/staff/places")
    place = {"name": "Test University", "kind": "college", "domains": ["testu.edu"]}
    slug = c.call("POST", "/api/staff/places", json=place)["places"][0]["slug"]
    c.call("POST", "/api/staff/places/requests/decline", json={"domain": "other.org"})
    c.call("GET", "/api/places")
    c.call("GET", "/api/me/places")
    c.call("POST", "/api/me/places/start", json={"email": "ana@testu.edu"})
    mailer = client.app.state.mailer
    client.portal.call(mailer.drain)
    code = re.search(r"\b(\d{6})\b", mailer.sent[-1][1].text).group(1)
    c.call("POST", "/api/me/places/confirm", json={"code": code})
    c.call("POST", f"/api/me/places/{slug}/remove", "/api/me/places/{slug}/remove")
    c.call("POST", "/api/me/mfa/backup-codes", json={"code": backup[0]})
    c.call("POST", "/api/me/mfa/disable", json={"password": PW, "code": "nope"})  # error body
    fresh = mfa.totp_at(setup["secret"], int(time.time()) // mfa.TOTP_STEP + 1)  # the next step's code
    c.call("POST", "/api/me/mfa/disable", json={"password": PW, "code": fresh})
    c.call("POST", "/api/me/email", json={"email": "ana@example.com", "password": PW})
    c.call("POST", "/api/me/email/resend")
    mailer = client.app.state.mailer
    client.portal.call(mailer.drain)
    token = re.search(r"#([A-Za-z0-9_-]{20,})", mailer.sent[-1][1].text).group(1)
    c.call("POST", "/api/auth/verify", json={"token": token})
    c.call("POST", "/api/auth/verify", json={"token": token})  # spent: the error body
    c.call("POST", "/api/auth/email-link", json={"email": "ana@example.com"})
    c.call("POST", "/api/auth/email-link/use", json={"token": "x" * 30})  # unknown: the error body
    c.call("POST", "/api/auth/forgot", json={"login": "Ana_99"})
    client.portal.call(mailer.drain)
    reset = re.search(r"#([A-Za-z0-9_-]{20,})", mailer.sent[-1][1].text).group(1)
    c.call("POST", "/api/auth/reset", json={"token": reset, "new_password": PW})
    c.call("GET", "/api/me/sessions")
    c.call("GET", "/api/me/identities")
    c.call("GET", "/api/ratings/me")
    c.call("GET", "/api/me/coins")
    c.call("GET", "/api/me/battles")
    c.call("GET", "/api/me/progress")
    c.call("GET", "/api/billing/config")
    c.call("GET", "/api/me/happening")
    c.call("GET", "/api/categories")
    c.call("POST", "/api/billing/checkout")  # payments are off here: an error body
    c.call("POST", "/api/billing/paddle", content=b"{}")  # unsigned: refused
    c.call("GET", "/api/me/plus")
    c.call("POST", "/api/me/plus/manage")  # nothing to manage: an error body
    c.call(
        "POST", "/api/me/quests/win1/claim", "/api/me/quests/{quest}/claim"
    )  # not done yet: the error body
    c.call("POST", "/api/me/quests/nope/reroll", "/api/me/quests/{quest}/reroll")  # not today's: error body
    c.call("POST", "/api/me/weekly/nope/claim", "/api/me/weekly/{challenge}/claim")
    c.call("POST", "/api/me/season/nope/claim", "/api/me/season/{challenge}/claim")
    c.call("GET", "/api/ratings/board?game=chess&period=week", "/api/ratings/board")
    c.call("POST", "/api/me/place-boards", json={"on": True})
    c.call("POST", "/api/me/google/remove", json={"password": PW})  # nothing linked: still ok
    assert c.redirect("/api/auth/google/start") == "/account?google=off"
    assert c.redirect("/api/auth/google/callback?code=x&state=y") == "/account?google=off"
    c.call("POST", "/api/me/sessions/abcdef012345/revoke", "/api/me/sessions/{session_id}/revoke")  # error
    c.call("POST", "/api/me/sessions/revoke")
    c.call("POST", "/api/me/email/remove", json={"password": PW})
    c.call("POST", "/api/me/password", json={"password": PW, "new_password": PW + "!"})
    c.call(
        "POST",
        "/api/auth/recover",
        json={"username": "Ana_99", "recovery_code": made["recovery_code"], "new_password": PW},
    )
    c.call("POST", "/api/me/delete", json={"password": PW})

    missed = set(c.models) - c.called
    assert not missed, f"routes the contract test never called: {sorted(missed)}"


def test_the_openapi_document_names_every_response():
    """Each API route's 200/201 response points at a named schema the apps can generate a type from."""
    from app.config import Settings

    doc = create_app(Settings(secret_key="t" * 40)).openapi()
    for path, ops in doc["paths"].items():
        if not path.startswith("/api/"):
            continue
        for method, op in ops.items():
            ok = op["responses"].get("201") or op["responses"].get("200")
            schema = ok["content"]["application/json"]["schema"]
            assert schema != {}, f"{method.upper()} {path} has no response schema"
