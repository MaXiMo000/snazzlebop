"""Authenticator-app sign-in end to end: set-up needs the password and a working code, sign-in then needs
a code (each code works once), backup codes work once each, and recovery, deletion and switching it off
all need the second step too."""

from __future__ import annotations

import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app import mfa  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.test_api import settings  # noqa: E402

PW = "correct horse battery"


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(settings(tmp_path, rate_auth_burst=1000))) as c:
        yield c


def now_code(secret: str, ahead: int = 0) -> str:
    return mfa.totp_at(secret, int(time.time()) // mfa.TOTP_STEP + ahead)


def turn_on(client) -> tuple[str, list[str], str]:
    made = client.post("/api/auth/signup", json={"username": "Ana_99", "password": PW}).json()
    assert client.post("/api/me/mfa/setup", json={"password": "wrong password"}).status_code == 401
    setup = client.post("/api/me/mfa/setup", json={"password": PW}).json()
    assert len(setup["qr"]) > 20 and setup["uri"].startswith("otpauth://totp/Snazzlebop%3AAna_99")
    assert client.get("/api/me/mfa").json() == {"enabled": False, "backup_codes_left": 0}  # not yet
    r = client.post("/api/me/mfa/enable", json={"code": "123456"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "bad_code"
    codes = client.post("/api/me/mfa/enable", json={"code": now_code(setup["secret"])}).json()["codes"]
    assert len(codes) == 10
    assert client.get("/api/me/mfa").json() == {"enabled": True, "backup_codes_left": 10}
    return setup["secret"], codes, made["recovery_code"]


def login(client, code=None):
    body = {"username": "Ana_99", "password": PW} | ({"code": code} if code is not None else {})
    return client.post("/api/auth/login", json=body)


def test_sign_in_needs_a_code_once_it_is_on_and_each_code_works_once(client):
    secret, _, _ = turn_on(client)
    client.post("/api/auth/logout")
    r = login(client)
    assert r.status_code == 401 and r.json()["error"]["code"] == "mfa_required"
    assert client.get("/api/me").json()["user"] is None  # no session without the code
    assert login(client, "000000").json()["error"]["code"] == "bad_code"
    code = now_code(secret, ahead=1)
    assert login(client, code).status_code == 200
    client.post("/api/auth/logout")
    assert login(client, code).json()["error"]["code"] == "bad_code"  # replayed: refused


def test_a_backup_code_works_once_and_new_ones_replace_the_old(client):
    secret, codes, _ = turn_on(client)
    client.post("/api/auth/logout")
    assert login(client, codes[0].lower()).status_code == 200
    client.post("/api/auth/logout")
    assert login(client, codes[0]).status_code == 401  # spent
    assert login(client, codes[1]).status_code == 200
    assert client.get("/api/me/mfa").json()["backup_codes_left"] == 8
    fresh = client.post("/api/me/mfa/backup-codes", json={"code": now_code(secret, ahead=1)}).json()["codes"]
    assert set(fresh).isdisjoint(codes)
    client.post("/api/auth/logout")
    assert login(client, codes[2]).status_code == 401  # the old set is gone
    assert login(client, fresh[0]).status_code == 200


def test_recovery_deletion_and_switching_off_need_the_second_step(client):
    secret, codes, recovery = turn_on(client)
    r = client.post("/api/me/delete", json={"password": PW})
    assert r.json()["error"]["code"] == "mfa_required"
    client.post("/api/auth/logout")
    body = {"username": "Ana_99", "recovery_code": recovery, "new_password": PW}
    assert client.post("/api/auth/recover", json=body).json()["error"]["code"] == "mfa_required"
    r = client.post("/api/auth/recover", json=body | {"code": codes[0]})
    assert r.status_code == 200  # the password is reset; the authenticator stays on
    assert client.get("/api/me/mfa").json()["enabled"] is True
    off = {"password": PW, "code": "999999"}
    assert client.post("/api/me/mfa/disable", json=off).status_code == 401
    assert (
        client.post("/api/me/mfa/disable", json=off | {"code": now_code(secret, ahead=1)}).status_code == 200
    )
    client.post("/api/auth/logout")
    assert login(client).status_code == 200  # back to the password alone


def test_setup_cant_replace_a_working_authenticator(client):
    turn_on(client)
    r = client.post("/api/me/mfa/setup", json={"password": PW})
    assert r.status_code == 409 and r.json()["error"]["code"] == "mfa_on"


def test_wrong_codes_count_towards_the_lockout(client):
    turn_on(client)
    client.post("/api/auth/logout")
    statuses = [login(client, "000000").status_code for _ in range(12)]
    assert statuses[-1] == 429  # locked, like wrong passwords
