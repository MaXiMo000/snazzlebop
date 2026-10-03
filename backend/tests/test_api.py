"""HTTP + WebSocket integration tests (need fastapi/httpx; skipped if not installed)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def settings(tmp_path, **kw):
    base = dict(
        secret_key="t" * 40,
        database_url="sqlite+aiosqlite:///:memory:",
        static_dir=str(tmp_path / "static"),
        trusted_proxy_hops=0,
        rate_default_burst=1000,
        rate_create_burst=1000,
        rate_join_burst=1000,
    )
    base.update(kw)
    return Settings(**base)


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        yield c


def make_room(client, name="Host"):
    r = client.post("/api/rooms", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def join(client, code, name):
    r = client.post(f"/api/rooms/{code}/join", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()


def auth(ws, token):
    ws.send_json({"t": "auth", "token": token})
    return ws.receive_json()


def test_health_and_security_headers(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"ok": True}
    h = r.headers
    assert "default-src 'none'" in h["content-security-policy"]
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["cross-origin-embedder-policy"] == "require-corp"  # ZAP 90004
    assert "server" not in {k.lower() for k in h}
    assert client.get("/robots.txt").headers["cache-control"] == "no-store"  # ZAP 10049 on 404s


def test_bad_host_rejected(tmp_path):
    with TestClient(create_app(settings(tmp_path)), base_url="http://evil.example") as c:
        assert c.get("/api/games").status_code == 400


def test_games_catalog(client):
    games = client.get("/api/games").json()
    assert {g["id"] for g in games} == {
        "frenemy",
        "alibi",
        "price",
        "telepathy",
        "mural",
        "blackjack",
        "crossword",
        "dice",
        "split",
        "chicken",
        "wits",
    }


def test_create_room_validation_and_no_echo(client):
    assert client.post("/api/rooms", json={"name": "<script>"}).status_code == 400
    r = client.post("/api/rooms", json={"name": "ok", "admin": True})
    assert r.status_code == 422
    assert "admin" not in r.text  # validation errors must not echo input
    assert (
        client.post(
            "/api/rooms", content=b"not json", headers={"content-type": "application/json"}
        ).status_code
        == 422
    )


def test_body_too_large(client):
    r = client.post("/api/rooms", json={"name": "x" * 5000})
    assert r.status_code == 413


def test_room_code_guessing_gets_rate_limited(tmp_path):
    s = settings(tmp_path, rate_join_burst=10, rate_join_per_min=1)
    with TestClient(create_app(s)) as c:
        codes = [c.post("/api/rooms/ZZZZZ/join", json={"name": "a"}).status_code for _ in range(8)]
    assert codes[0] == 404
    assert 429 in codes


def test_production_hides_docs(tmp_path):
    # With a built SPA present, like the real image: the catch-all must not answer for these.
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "index.html").write_text("<html>app</html>")
    s = settings(
        tmp_path, env="production", allowed_hosts=("testserver",), allowed_origins=("https://testserver",)
    )
    with TestClient(create_app(s)) as c:
        for path in ("/docs", "/openapi.json", "/redoc", "/admin", "/r/ABCDE/extra"):
            assert c.get(path).status_code == 404, path
        assert c.get("/").status_code == 200
        assert c.get("/r/ABCDE").status_code == 200
        head = c.head("/")
        assert head.status_code == 200 and "frame-ancestors 'none'" in head.headers["content-security-policy"]
        assert "strict-transport-security" in c.get("/healthz").headers


def test_spa_fallback_and_no_path_traversal(tmp_path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>app</html>")
    (static / "assets" / "a.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("TOPSECRET")
    with TestClient(create_app(settings(tmp_path))) as c:
        assert "app" in c.get("/r/ABCDE").text
        assert c.get("/assets/a.js").headers["cache-control"].startswith("public")
        for evil in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt", "/assets/../../secret.txt"):
            assert "TOPSECRET" not in c.get(evil).text
        assert c.get("/api/nope").status_code == 404


def test_ws_requires_valid_auth(client):
    room = make_room(client)
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(f"/ws/{room['code']}") as ws:
        ws.send_json({"t": "auth", "token": "garbage"})
        ws.receive_json()
    other = make_room(client, "Other")
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(f"/ws/{room['code']}") as ws,
    ):  # token for a different room
        ws.send_json({"t": "auth", "token": other["token"]})
        ws.receive_json()
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/ZZZZZ") as ws:  # unknown room
        ws.send_json({"t": "auth", "token": room["token"]})
        ws.receive_json()


def test_ws_origin_enforced_in_production(tmp_path):
    s = settings(
        tmp_path, env="production", allowed_hosts=("testserver",), allowed_origins=("https://testserver",)
    )
    with TestClient(create_app(s)) as c:
        room = c.post("/api/rooms", json={"name": "Host"}, headers={"origin": "https://testserver"}).json()
        with (
            pytest.raises(WebSocketDisconnect),
            c.websocket_connect(f"/ws/{room['code']}", headers={"origin": "https://evil.example"}),
        ):
            pass
        with (
            pytest.raises(WebSocketDisconnect),
            c.websocket_connect(f"/ws/{room['code']}"),
        ):  # no Origin at all is refused in production
            pass
        with c.websocket_connect(f"/ws/{room['code']}", headers={"origin": "https://testserver"}) as ws:
            assert auth(ws, room["token"])["t"] == "state"


def test_ws_message_limits(tmp_path):
    s = settings(tmp_path, ws_msg_burst=5, ws_msgs_per_second=0.01)
    with TestClient(create_app(s)) as c:
        room = make_room(c)
        with c.websocket_connect(f"/ws/{room['code']}") as ws:
            assert auth(ws, room["token"])["t"] == "state"
            for _ in range(50):
                ws.send_json({"t": "ping"})
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()  # the server never answers pings; the flood closes the socket
        room2 = make_room(c, "Big")
        with c.websocket_connect(f"/ws/{room2['code']}") as ws:
            auth(ws, room2["token"])
            ws.send_text("x" * 5000)
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()


def test_ws_per_ip_cap(tmp_path):
    s = settings(tmp_path, max_ws_per_ip=2)
    with TestClient(create_app(s)) as c:
        room = make_room(c)
        a = join(c, room["code"], "A")
        with (
            c.websocket_connect(f"/ws/{room['code']}") as w1,
            c.websocket_connect(f"/ws/{room['code']}") as w2,
        ):
            auth(w1, room["token"])
            auth(w2, a["token"])
            with pytest.raises(WebSocketDisconnect), c.websocket_connect(f"/ws/{room['code']}"):
                pass


def test_full_price_game_over_websockets(client):
    host = make_room(client)
    guest = join(client, host["code"], "Guest")
    with (
        client.websocket_connect(f"/ws/{host['code']}") as wh,
        client.websocket_connect(f"/ws/{host['code']}") as wg,
    ):
        sh = auth(wh, host["token"])
        assert sh["room"]["phase"] == "lobby" and sh["you"] == host["player_id"]
        auth(wg, guest["token"])
        wh.receive_json()  # host sees guest connect
        wg.send_json({"t": "start", "game": "price"})
        err = wg.receive_json()
        assert err["t"] == "error" and err["code"] == "not_host"
        wh.send_json({"t": "start", "game": "price"})
        state = wh.receive_json()
        assert state["room"]["phase"] == "game" and state["game"]["phase"] == "guess"
        assert "true_price" not in str(state)
        wh.send_json({"t": "act", "a": "guess", "amount": 100})
        wg.send_json({"t": "act", "a": "guess", "amount": 200})
        last = None
        for _ in range(6):
            last = wh.receive_json()
            if last.get("game", {}).get("phase") == "reveal":
                break
        assert last["game"]["phase"] == "reveal"
        assert "true_price" in last["game"]["result"]


def test_stats_endpoint(client):
    assert isinstance(client.get("/api/stats").json(), dict)


def close_code(c, code, token):
    with pytest.raises(WebSocketDisconnect) as exc, c.websocket_connect(f"/ws/{code}") as ws:
        ws.send_json({"t": "auth", "token": token})
        ws.receive_json()
    return exc.value.code


def test_ws_room_guessing_is_indistinguishable_and_penalised(tmp_path):
    s = settings(tmp_path, rate_join_burst=12, rate_join_per_min=0.001)
    with TestClient(create_app(s)) as c:
        room = make_room(c)
        # A wrong code must look exactly like a wrong token, or sockets become a free code oracle.
        assert close_code(c, "ZZZZZ", room["token"]) == 1008
        assert close_code(c, room["code"], "garbage") == 1008
        for _ in range(3):
            close_code(c, "ZZZZZ", room["token"])
        # The guesser is now in the penalty box on both channels, even with a valid token.
        assert c.post(f"/api/rooms/{room['code']}/join", json={"name": "X"}).status_code == 429
        with pytest.raises(WebSocketDisconnect), c.websocket_connect(f"/ws/{room['code']}") as ws:
            auth(ws, room["token"])


def test_ws_stale_but_genuine_token_is_not_penalised(tmp_path):
    # After a restart/expiry every tab reconnects with a real token for a dead room. A party on one
    # NAT must not lock itself out of creating the next room.
    s = settings(tmp_path, rate_join_burst=12, rate_join_per_min=0.001)
    app = create_app(s)
    with TestClient(app) as c:
        room = make_room(c)
        app.state.hub.rooms.clear()
        for _ in range(6):
            assert close_code(c, room["code"], room["token"]) == 1008
        fresh = make_room(c)
        assert c.post(f"/api/rooms/{fresh['code']}/join", json={"name": "X"}).status_code == 200


def test_tv_mode_endpoint_and_socket(tmp_path):
    s = settings(tmp_path, rate_join_burst=12, rate_join_per_min=0.001)
    with TestClient(create_app(s)) as c:
        room = make_room(c)
        r = c.post(f"/api/rooms/{room['code'].lower()}/tv")
        assert r.status_code == 200 and set(r.json()) == {"code", "token"}
        with c.websocket_connect(f"/ws/{room['code']}") as ws:
            state = auth(ws, r.json()["token"])
            assert state["tv"] is True and state["you"].startswith("tv:")
            assert room["player_id"] in [p["id"] for p in state["players"]]
            ws.send_json({"t": "start", "game": "price"})
            assert ws.receive_json() == {"t": "error", "code": "read_only", "message": "TV mode is read-only"}
        # Guessing codes through the TV endpoint costs the same as through join.
        assert c.post("/api/rooms/ZZZZZ/tv").status_code == 404
        statuses = [c.post("/api/rooms/ZZZZZ/tv").status_code for _ in range(3)]
        assert 429 in statuses


def test_audience_endpoint_and_socket(tmp_path):
    s = settings(tmp_path, rate_join_burst=12, rate_join_per_min=0.001)
    with TestClient(create_app(s)) as c:
        room = make_room(c)
        r = c.post(f"/api/rooms/{room['code']}/audience", json={"name": "Fan"})
        assert r.status_code == 200 and set(r.json()) == {"code", "player_id", "token"}
        assert r.json()["player_id"].startswith("au:")
        with c.websocket_connect(f"/ws/{room['code']}") as ws:
            state = auth(ws, r.json()["token"])
            assert state["role"] == "audience" and state["tv"] is False
            assert state["crowd"]["members"] == [
                {"id": r.json()["player_id"], "name": "Fan", "points": 0, "connected": True}
            ]
            ws.send_json({"t": "start", "game": "price"})
            assert ws.receive_json()["code"] == "audience_only"
            ws.send_json({"t": "react", "e": "🔥"})
            assert ws.receive_json()["reactions"][-1] == {"id": 1, "e": "🔥", "by": "Fan"}
        assert c.post(f"/api/rooms/{room['code']}/audience", json={"name": "<b>"}).status_code == 400
        # Guessing codes through the audience endpoint costs the same as through join.
        assert c.post("/api/rooms/ZZZZZ/audience", json={"name": "Fan"}).status_code == 404
        statuses = [c.post("/api/rooms/ZZZZZ/audience", json={"name": "Fan"}).status_code for _ in range(3)]
        assert 429 in statuses
