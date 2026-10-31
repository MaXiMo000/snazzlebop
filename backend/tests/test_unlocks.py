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
            P.clean_look({"frame": "gold", "win": "disco"}, 12, False),
            {"frame": "gold", "char": "none", "win": "disco"},
        )
        self.assertEqual(P.clean_look({"frame": "gold", "win": "crown"}, 5, False), P.DEFAULT_LOOK)
        self.assertEqual(P.clean_look({"frame": "plus"}, 99, False)["frame"], "none")  # Plus lapsed
        self.assertEqual(P.clean_look({"frame": "plus"}, 1, True)["frame"], "plus")
        self.assertEqual(P.clean_look("junk", 50, True), P.DEFAULT_LOOK)
        self.assertEqual(P.clean_look({"frame": ["x"], "win": None}, 50, True), P.DEFAULT_LOOK)

    def test_shop_looks_need_buying(self):
        owned = P.owned_looks({"look_frame_inferno": 1, "look_char_dragon": 0, "trivia_fifty": 3})
        self.assertEqual(owned, frozenset({"look_frame_inferno"}))
        look = P.clean_look({"frame": "inferno", "char": "dragon"}, 99, True, owned)
        self.assertEqual((look["frame"], look["char"]), ("inferno", "none"))  # Plus doesn't buy shop looks
        self.assertEqual(P.owned_looks("junk"), frozenset())

    def test_every_look_is_complete(self):
        for kind, table in P.LOOKS.items():
            self.assertIn(P.DEFAULT_LOOK[kind], table)
            for pick, (name, how, amount) in table.items():
                self.assertTrue(name and len(pick) <= 16, pick)
                self.assertIn(how, ("level", "plus", "shop"))
                self.assertTrue(amount > 0 if how != "plus" else amount == 0, pick)
            self.assertEqual(P.LOOKS[kind][P.DEFAULT_LOOK[kind]][1:], ("level", 1))


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


def test_shop_looks_are_bought_once_then_worn(client):
    signup(client)
    item = P.shop_id("frame", "inferno")
    price = P.LOOK_PRICES[item]
    assert client.post("/api/me/look", json={"frame": "inferno", "win": "confetti"}).status_code == 403
    shop = {i["id"]: i for i in client.get("/api/shop").json()["items"]}
    assert shop[item]["price"] == price and shop[item]["game"] == "Looks"
    set_user(client, coins=price - 1)
    assert client.post("/api/shop/buy", json={"item": item}).status_code == 400  # not enough coins
    set_user(client, coins=price + 10)
    r = client.post("/api/shop/buy", json={"item": item})
    assert r.status_code == 200 and r.json()["user"]["coins"] == 10
    assert (
        client.post("/api/shop/buy", json={"item": item}).json()["error"]["code"] == "owned"
    )  # kept, never twice
    look = client.get("/api/me/look").json()
    assert {f["id"]: f["unlocked"] for f in look["frames"]}["inferno"] is True
    r = client.post("/api/me/look", json={"frame": "inferno", "win": "confetti", "char": "none"})
    assert r.status_code == 200 and r.json()["frame"] == "inferno"
    # a character: level ones open with levels, and leaving it out keeps the current one
    assert (
        client.post("/api/me/look", json={"frame": "none", "win": "confetti", "char": "robot"}).status_code
        == 403
    )
    set_user(client, xp=P.xp_for(4))
    assert (
        client.post("/api/me/look", json={"frame": "inferno", "win": "confetti", "char": "robot"}).json()[
            "char"
        ]
        == "robot"
    )
    assert client.post("/api/me/look", json={"frame": "none", "win": "confetti"}).json()["char"] == "robot"
    assert (
        client.post("/api/me/look", json={"frame": "none", "win": "confetti", "char": "dragon"}).status_code
        == 403
    )
    assert client.post("/api/me/look", json={"frame": "none", "win": "x" * 17}).status_code == 422
