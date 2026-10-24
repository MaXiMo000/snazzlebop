"""Presence, "up for a game" and notifications over HTTP: matching three members, who gets told, tapping
through into one room, muting, limits, quiet hours, pushes (with a stand-in push service), the inbox,
settings, and inviting friends and clubmates to a room."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import webpush  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.test_api import settings  # noqa: E402

PW = "correct horse battery"
NAMES = ["Ana_99", "Bo_42", "Cy_77", "Di_55", "Ed_11"]


class FakePush:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, str]]] = []
        self.gone: set[str] = set()

    def __call__(self, vapid, endpoint, p256dh, auth, payload) -> None:
        assert vapid.header(endpoint).startswith("vapid t=")
        if endpoint in self.gone:
            raise webpush.Gone("410")
        self.sent.append((endpoint, payload))


@pytest.fixture()
def client(tmp_path):
    app = create_app(settings(tmp_path, rate_auth_burst=1000))
    with TestClient(app) as c:
        c.push = FakePush()
        app.state.notifier.sender = c.push
        yield c


def be(client, name):
    client.post("/api/auth/logout")
    if client.post("/api/auth/login", json={"username": name, "password": PW}).status_code != 200:
        assert client.post("/api/auth/signup", json={"username": name, "password": PW}).status_code == 201


def drain(client):
    client.portal.call(client.app.state.notifier.drain)


def club_with(client, names=NAMES, rules=None):
    be(client, names[0])
    slug = client.post("/api/clubs", json={"name": "Hostel Four", "rules": rules or {}}).json()["slug"]
    code = client.post(f"/api/clubs/{slug}/invites", json={}).json()["code"]
    for n in names[1:]:
        be(client, n)
        assert client.post("/api/clubs/join", json={"code": code}).status_code == 200
    return slug


def inbox(client, name):
    be(client, name)
    return client.get("/api/notifications").json()


def subscribe(client, name, endpoint):
    be(client, name)
    key = ec.generate_private_key(ec.SECP256R1()).public_key()
    point = webpush.b64u(webpush._point(key))
    body = {"endpoint": endpoint, "p256dh": point, "auth": webpush.b64u(b"0123456789abcdef")}
    assert client.post("/api/push/subscribe", json=body).json() == {"ok": True}


def test_three_up_make_a_game_and_the_club_hears_once(client):
    slug = club_with(client)
    subscribe(client, "Di_55", "https://fcm.googleapis.com/fcm/send/di")
    be(client, "Ed_11")
    client.post(f"/api/clubs/{slug}/mute", json={"muted": True})

    be(client, "Ana_99")
    r = client.post(f"/api/clubs/{slug}/up", json={"game": "imposter", "minutes": 60}).json()
    assert r["up"]["mine"]["game"] == "imposter" and r["up"]["count"] == 1 and r["up"]["match"] is None
    be(client, "Bo_42")
    client.post(f"/api/clubs/{slug}/up", json={"game": None, "minutes": 30})
    assert inbox(client, "Di_55")["items"] == []  # two isn't enough: nobody is told
    be(client, "Cy_77")
    r = client.post(f"/api/clubs/{slug}/up", json={"game": "imposter", "minutes": 120}).json()
    assert r["up"]["match"] == {"game": "imposter", "players": 3, "room": None, "mine": True}
    statuses = {m["username"]: (m["status"], m["up_game"]) for m in r["members"]}
    assert statuses["Ana_99"] == ("up", "imposter") and statuses["Bo_42"] == ("up", None)
    drain(client)

    di = inbox(client, "Di_55")
    assert di["unread"] == 1 and di["items"][0]["title"] == "Game on in Hostel Four!"
    assert "3 people want to play Imposter" in di["items"][0]["body"]
    assert di["items"][0]["link"] == f"/clubs/{slug}"
    assert [e for e, _ in client.push.sent] == ["https://fcm.googleapis.com/fcm/send/di"]
    assert client.push.sent[0][1]["url"] == f"/clubs/{slug}"
    assert inbox(client, "Ed_11")["items"] == []  # muted this club

    # Tap through: the first opens the room and hosts it, the next joins the same room.
    be(client, "Bo_42")
    first = client.post(f"/api/clubs/{slug}/up/go", json={"name": "Bo"})
    assert first.status_code == 201
    be(client, "Di_55")  # wasn't up, but a clubmate can join while there's a seat
    second = client.post(f"/api/clubs/{slug}/up/go", json={"name": "Di"})
    assert second.json()["code"] == first.json()["code"]
    detail = client.get(f"/api/clubs/{slug}").json()
    assert detail["up"]["match"]["room"] == first.json()["code"]


def test_no_match_no_room_and_cancelling(client):
    slug = club_with(client, NAMES[:3])
    be(client, "Ana_99")
    assert client.post(f"/api/clubs/{slug}/up/go", json={"name": "Ana"}).json()["error"]["code"] == "no_match"
    client.post(f"/api/clubs/{slug}/up", json={"game": None, "minutes": 60})
    r = client.post(f"/api/clubs/{slug}/up/cancel").json()
    assert r["up"]["mine"] is None and r["up"]["count"] == 0
    for bad in (
        {"game": None, "minutes": 45},
        {"game": "nope", "minutes": 60},
        {"game": None, "minutes": "60"},
    ):
        assert client.post(f"/api/clubs/{slug}/up", json=bad).status_code in (400, 422), bad


def test_only_the_club_games(client):
    slug = club_with(client, NAMES[:3], rules={"games": ["trivia"]})
    be(client, "Ana_99")
    r = client.post(f"/api/clubs/{slug}/up", json={"game": "imposter", "minutes": 60})
    assert r.json()["error"]["code"] == "bad_game"
    assert client.post(f"/api/clubs/{slug}/up", json={"game": "trivia", "minutes": 60}).status_code == 200


def test_settings_quiet_hours_caps_and_dead_subscriptions(client):
    app = client.app
    slug = club_with(client, NAMES[:3])
    subscribe(client, "Cy_77", "https://updates.push.services.mozilla.com/wpush/v2/cy")
    r = client.post("/api/me/notify", json={"types": {"invite": False}, "hidden": True})
    assert r.json()["hidden"] is True and {k["id"]: k["on"] for k in r.json()["kinds"]} == {
        "club_up": True,
        "invite": False,
    }
    assert r.json()["devices"] == 1
    assert client.post("/api/me/notify", json={"types": {"spam": True}}).status_code == 400

    notifier = app.state.notifier
    send = lambda: client.portal.call(  # noqa: E731
        notifier.notify, [3], "club_up", "T", "B", "/clubs/x", None, (1, None)
    )
    # Quiet hours (Cy's own, in Cy's time): in the inbox, but no push.
    client.post("/api/me/notify", json={"quiet": {"from": "00:00", "to": "23:59"}, "tz": 0})
    notifier.clock = lambda: datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    assert send() == [3]
    drain(client)
    assert client.push.sent == []
    client.post("/api/me/notify", json={"clear_quiet": True})
    assert send() == [3]
    drain(client)
    assert len(client.push.sent) == 1
    assert send() == [3]
    assert send() == []  # 3 a day per club for "a club game is filling up"
    # A subscription the push service says is gone is dropped.
    client.push.gone.add("https://updates.push.services.mozilla.com/wpush/v2/cy")
    assert client.portal.call(notifier.notify, [3], "club_up", "T", "B", "/x", None, (2, None)) == [3]
    drain(client)
    assert client.get("/api/me/notify").json()["devices"] == 0
    # Invites switched off: nothing at all.
    assert client.portal.call(notifier.notify, [3], "invite", "T", "B", "/r/X") == []
    assert slug


def test_the_daily_push_cap(client):
    club_with(client, NAMES[:1])
    subscribe(client, "Ana_99", "https://fcm.googleapis.com/fcm/send/ana")
    notifier = client.app.state.notifier
    for club in range(4):
        for _ in range(3):
            client.portal.call(notifier.notify, [1], "club_up", "T", "B", "/x", None, (club, None))
    drain(client)
    assert len(client.push.sent) == 8  # 12 notifications, 8 pushes
    assert client.get("/api/notifications").json()["unread"] == 12


def test_grouping_and_the_inbox(client):
    club_with(client, NAMES[:1])
    notifier = client.app.state.notifier
    for n in (3, 4):
        client.portal.call(notifier.notify, [1], "club_up", "T", f"{n} people", "/x", "g1", (1, None))
    box = client.get("/api/notifications").json()
    assert [i["body"] for i in box["items"]] == ["4 people"] and box["unread"] == 1  # one, updated
    client.portal.call(notifier.notify, [1], "club_up", "T", "other", "/x", "g2", (1, None))
    box = client.get("/api/notifications").json()
    assert box["unread"] == 2 and len(box["push_key"]) > 80
    assert all(i["at"].endswith("+00:00") for i in box["items"])  # times always carry their zone
    first = box["items"][0]["id"]
    assert client.post("/api/notifications/read", json={"ids": [first]}).json() == {"ok": True}
    assert client.get("/api/notifications").json()["unread"] == 1
    client.post("/api/notifications/read", json={})
    assert client.get("/api/notifications").json()["unread"] == 0


def test_push_subscriptions_only_on_push_services(client):
    be(client, "Ana_99")
    key = webpush.b64u(webpush._point(ec.generate_private_key(ec.SECP256R1()).public_key()))
    auth = webpush.b64u(b"0123456789abcdef")
    for endpoint in ("https://evil.test/x", "http://fcm.googleapis.com/x", "https://localhost/x"):
        r = client.post("/api/push/subscribe", json={"endpoint": endpoint, "p256dh": key, "auth": auth})
        assert r.json()["error"]["code"] == "bad_subscription", endpoint
    r = client.post(
        "/api/push/subscribe",
        json={"endpoint": "https://fcm.googleapis.com/x", "p256dh": "nope", "auth": auth},
    )
    assert r.json()["error"]["code"] == "bad_subscription"
    ok = {"endpoint": "https://fcm.googleapis.com/x", "p256dh": key, "auth": auth}
    assert client.post("/api/push/subscribe", json=ok).json() == {"ok": True}
    assert client.get("/api/me/notify").json()["devices"] == 1
    assert client.post("/api/push/unsubscribe", json={"endpoint": ok["endpoint"]}).json() == {"ok": True}
    assert client.get("/api/me/notify").json()["devices"] == 0


def test_presence_online_hidden_and_friends(client):
    slug = club_with(client, NAMES[:2])
    be(client, "Ana_99")
    client.post("/api/friends", json={"username": "Bo_42"})
    be(client, "Bo_42")
    client.post("/api/friends", json={"username": "Ana_99"})
    client.get("/api/notifications")  # the app's poll: Bo is online
    be(client, "Ana_99")
    assert client.get("/api/friends").json()["friends"] == [
        {"username": "Bo_42", "room": None, "status": "online"}
    ]
    detail = client.get(f"/api/clubs/{slug}").json()
    assert all(m["joined_at"].endswith("+00:00") for m in detail["members"])
    members = {m["username"]: m["status"] for m in detail["members"]}
    assert members["Bo_42"] == "online"
    be(client, "Bo_42")
    client.post("/api/me/notify", json={"hidden": True})
    be(client, "Ana_99")
    assert client.get("/api/friends").json()["friends"][0]["status"] == "offline"


def test_inviting_friends_and_clubmates_to_a_room(client):
    slug = club_with(client, NAMES[:3])
    be(client, "Di_55")  # neither a friend nor a clubmate
    be(client, "Ed_11")
    client.post("/api/friends", json={"username": "Ana_99"})
    be(client, "Ana_99")
    client.post("/api/friends", json={"username": "Ed_11"})
    be(client, "Ana_99")
    room = client.post(f"/api/clubs/{slug}/rooms", json={"name": "Ana"}).json()["code"]
    people = client.get(f"/api/rooms/{room}/invitees").json()["people"]
    assert sorted((p["username"], p["why"]) for p in people) == [
        ("Bo_42", "club"),
        ("Cy_77", "club"),
        ("Ed_11", "friend"),
    ]
    assert (
        client.post(f"/api/rooms/{room}/invite", json={"username": "Di_55"}).json()["error"]["code"]
        == "cant_invite"
    )
    assert client.post(f"/api/rooms/{room}/invite", json={"username": "ed_11"}).json() == {"ok": True}
    item = inbox(client, "Ed_11")["items"][0]
    assert item["title"] == "Ana_99 invites you to play (Hostel Four)" and item["link"] == f"/r/{room}"
    # Only someone seated in the room can invite people to it.
    assert (
        client.post(f"/api/rooms/{room}/invite", json={"username": "Ana_99"}).json()["error"]["code"]
        == "not_in_room"
    )
    assert client.get(f"/api/rooms/{room}/invitees").json()["error"]["code"] == "not_in_room"


def test_closing_a_club_or_leaving_clears_its_game(client):
    slug = club_with(client, NAMES[:4])
    for who in NAMES[:3]:
        be(client, who)
        client.post(f"/api/clubs/{slug}/up", json={"game": None, "minutes": 60})
    be(client, "Di_55")
    assert client.get(f"/api/clubs/{slug}").json()["up"]["match"]["players"] == 3
    be(client, "Cy_77")
    client.post(f"/api/clubs/{slug}/leave")
    be(client, "Di_55")
    assert client.get(f"/api/clubs/{slug}").json()["up"]["match"]["players"] == 2
    be(client, "Ana_99")
    client.post(f"/api/clubs/{slug}/delete")
    again = client.post("/api/clubs", json={"name": "Brand New"}).json()  # SQLite may reuse the id
    assert again["up"] == {"mine": None, "count": 0, "needed": 3, "match": None}
