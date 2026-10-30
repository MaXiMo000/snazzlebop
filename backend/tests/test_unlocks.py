"""Level unlocks: frames and victory animations open with levels (one with Plus), a locked or unknown
pick is refused, a lapsed unlock falls back to the default, and slots are 1, or 2 from level 10 or Plus."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app import progress as P
from app.db import User
from app.main import create_app
from tests.test_accounts import signup
from tests.test_api import settings


class RuleTests(unittest.TestCase):
    def test_slots(self):
        self.assertEqual(P.power_slots(1, False), 1)
        self.assertEqual(P.power_slots(P.SLOT_LEVEL - 1, False), 1)
        self.assertEqual(P.power_slots(P.SLOT_LEVEL, False), 2)
        self.assertEqual(P.power_slots(1, True), 2)

    def test_clean_look_keeps_only_unlocked_picks(self):
        self.assertEqual(
            P.clean_look({"frame": "gold", "win": "disco"}, 12, False), {"frame": "gold", "win": "disco"}
        )
        self.assertEqual(P.clean_look({"frame": "gold", "win": "crown"}, 5, False), P.DEFAULT_LOOK)
        self.assertEqual(P.clean_look({"frame": "plus"}, 99, False)["frame"], "none")  # Plus lapsed
        self.assertEqual(P.clean_look({"frame": "plus"}, 1, True)["frame"], "plus")
        self.assertEqual(P.clean_look("junk", 50, True), P.DEFAULT_LOOK)
        self.assertEqual(P.clean_look({"frame": ["x"], "win": None}, 50, True), P.DEFAULT_LOOK)


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(settings(tmp_path, rate_auth_burst=1000))) as c:
        yield c


def set_user(client, **values):
    db = client.app.state.db
    user = client.portal.call(db.user_by_name, "Ana_99")

    async def go():
        async with db.sessions() as session:
            await session.execute(update(User).where(User.id == user.id).values(**values))
            await session.commit()

    client.portal.call(go)


def test_picking_a_look_needs_the_level_or_plus(client):
    signup(client)
    look = client.get("/api/me/look").json()
    assert (look["level"], look["slots"], look["frame"], look["win"]) == (1, 1, "none", "confetti")
    assert {f["id"]: f["unlocked"] for f in look["frames"]}["bronze"] is False
    assert client.post("/api/me/look", json={"frame": "bronze", "win": "confetti"}).status_code == 403
    assert client.post("/api/me/look", json={"frame": "nope", "win": "confetti"}).status_code == 400
    assert client.post("/api/me/look", json={"frame": "none", "win": "confetti", "x": 1}).status_code == 422
    set_user(client, xp=P.xp_for(10))  # level 10: gold frame and a second slot
    r = client.post("/api/me/look", json={"frame": "gold", "win": "spotlight"})
    assert r.status_code == 200 and r.json()["frame"] == "gold" and r.json()["slots"] == 2
    assert client.post("/api/me/look", json={"frame": "plus", "win": "spotlight"}).status_code == 403
    set_user(client, plus_until=datetime.now(UTC) + timedelta(days=5))
    assert client.post("/api/me/look", json={"frame": "plus", "win": "spotlight"}).status_code == 200
    set_user(client, plus_until=datetime.now(UTC) - timedelta(days=1))  # Plus ran out
    assert client.get("/api/me/look").json()["frame"] == "none"
    client.post("/api/auth/logout")
    assert client.get("/api/me/look").status_code == 401
