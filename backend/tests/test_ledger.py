"""The coin ledger: every payout and purchase is one row, the cached balance always equals the sum, the
daily cap counts from the ledger, a reference can't be paid twice, and season rewards are paid once."""

from __future__ import annotations

import unittest

import pytest
from sqlalchemy import func, select

from app import ratings as R
from app.db import Database, LedgerEntry, SkillRating, User


def finish(uid, coins, place=1):
    return {"user_id": uid, "game_id": "trivia", "place": place, "players": 4, "points": 100, "coins": coins}


class LedgerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database("sqlite+aiosqlite:///:memory:")
        await self.db.init()
        self.ana = (await self.db.create_user("Ana_99", "x", "y")).id

    async def balance_matches(self, uid):
        async with self.db.sessions() as s:
            cached = (await s.get(User, uid)).coins
            summed = await s.scalar(
                select(func.coalesce(func.sum(LedgerEntry.delta), 0)).where(LedgerEntry.user_id == uid)
            )
        self.assertEqual(cached, summed)
        return cached

    async def test_payouts_purchases_and_the_cap(self):
        paid = await self.db.record_results([finish(self.ana, 50)], "2026-10", 120)
        self.assertEqual(paid, {self.ana: {"coins": 50, "note": ""}})
        await self.db.record_results([finish(self.ana, 50)], "2026-10", 120)
        paid = await self.db.record_results([finish(self.ana, 50)], "2026-10", 120)
        self.assertEqual(paid, {self.ana: {"coins": 20, "note": "limit"}})  # the cap, from the ledger
        self.assertEqual(await self.balance_matches(self.ana), 120)
        self.assertIsNotNone(await self.db.buy(self.ana, "peek", 40))
        self.assertIsNone(await self.db.buy(self.ana, "double", 400))
        self.assertEqual(await self.balance_matches(self.ana), 80)
        history = await self.db.coin_history(self.ana)
        self.assertEqual(history["balance"], 80)
        self.assertEqual(history["earned_today"], 120)  # spending doesn't give back cap room
        self.assertEqual([e["reason"] for e in history["entries"]], ["shop", "place", "place", "place"])
        self.assertEqual(history["entries"][0]["ref"], "peek")
        self.assertEqual((history["entries"][1]["game"], history["entries"][1]["place"]), ("trivia", 1))

    async def test_a_reference_is_paid_once(self):
        async with self.db.sessions() as s:
            self.assertTrue(await self.db._post(s, self.ana, 10, "season", "rating", "chess:3"))
            self.assertFalse(await self.db._post(s, self.ana, 10, "season", "rating", "chess:3"))
            await s.commit()
        self.assertEqual(await self.balance_matches(self.ana), 10)

    async def test_season_rewards(self):
        bo = (await self.db.create_user("Bo_42", "x", "y")).id
        last = R.season_of() - 1
        async with self.db.sessions() as s:
            for uid, mu in ((self.ana, 40.0), (bo, 26.0)):
                s.add(SkillRating(user_id=uid, game_id="chess", mu=mu, sigma=2.0, games=9, season=last))
            await s.commit()
        rows, paid = await self.db.my_ratings(self.ana)
        tier = R.tier(R.Rating(40, 2).display, 9)
        self.assertEqual(
            paid, [{"game": "chess", "season": last, "tier": tier, "coins": R.SEASON_REWARD[tier]}]
        )
        self.assertEqual((await self.db.my_ratings(self.ana))[1], [])  # once
        # Bo's reward comes with his first ranked game of the new season, before the reset
        await self.db.rate_match("chess", {self.ana: 2, bo: 1})
        bo_tier = R.tier(R.Rating(26, 2).display, 9)
        self.assertEqual(await self.balance_matches(bo), R.SEASON_REWARD[bo_tier])
        self.assertEqual((await self.db.my_ratings(bo))[1], [])
        self.assertEqual(await self.balance_matches(self.ana), R.SEASON_REWARD[tier])


pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from tests.test_api import settings  # noqa: E402


def test_coin_history_over_http(tmp_path):
    with TestClient(create_app(settings(tmp_path, rate_auth_burst=1000))) as client:
        assert client.get("/api/me/coins").status_code == 401
        client.post("/api/auth/signup", json={"username": "Ana_99", "password": "correct horse battery"})
        db = client.app.state.db
        uid = client.portal.call(db.user_by_name, "Ana_99").id
        client.portal.call(db.record_results, [finish(uid, 30, place=2)], "2026-10", 600)
        body = client.get("/api/me/coins").json()
        assert body["balance"] == 30 and body["earned_today"] == 30 and body["daily_cap"] == 600
        assert body["entries"][0]["reason"] == "place" and body["entries"][0]["place"] == 2
        export = client.get("/api/me/export").json()
        assert [e["reason"] for e in export["coins"]] == ["place"]
