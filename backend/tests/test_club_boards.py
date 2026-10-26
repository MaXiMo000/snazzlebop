"""A club's boards: the Legend board (each member's best rating this season) and the Club score
(activity, capped per day so it can't be farmed; only fair battles; members only)."""

from __future__ import annotations

import unittest

from app import progress as P
from app import ratings as R
from app.db import Club, Database, Membership, SkillRating


class ClubBoardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database("sqlite+aiosqlite:///:memory:")
        await self.db.init()
        self.ids = [(await self.db.create_user(f"B{i}_00", "x", "y")).id for i in range(4)]
        async with self.db.sessions() as s:
            club = Club(slug="b-1", name="B", about="", rules={}, created_by=self.ids[0])
            s.add(club)
            await s.flush()
            self.club = club.id
            for uid in self.ids[:3]:  # the fourth isn't a member
                s.add(Membership(club_id=club.id, user_id=uid, role="member"))
            await s.commit()

    async def test_the_legend_board_shows_each_members_best_rating(self):
        a, b, c, outsider = self.ids
        season = R.season_of()
        async with self.db.sessions() as s:
            for uid, game, mu, games in (
                (a, "chess", 30.0, 9),
                (a, "four", 34.0, 9),  # a's best
                (b, "chess", 40.0, 2),  # still placing: not listed
                (c, "trivia", 28.0, 6),
                (outsider, "chess", 50.0, 9),  # not in the club
            ):
                s.add(SkillRating(user_id=uid, game_id=game, mu=mu, sigma=3.0, games=games, season=season))
            await s.commit()
        rows = await self.db.club_legends(self.club)
        self.assertEqual([(r["username"], r["game"]) for r in rows], [("B0_00", "four"), ("B2_00", "trivia")])
        self.assertEqual(rows[0]["rating"], R.Rating(34.0, 3.0).display)

    async def test_the_club_score_is_activity_capped_per_day(self):
        a, b, _, outsider = self.ids
        for _ in range(30):  # a farming pair: only CLUB_DAY_GAMES a day count
            await self.db.log_activity([a, b], "club_game", self.club)
        await self.db.log_activity([a], "club_host", self.club)
        await self.db.log_activity([outsider], "club_game", self.club)  # not a member: no row
        await self.db.log_activity([b], "club_game", None)  # not in this club's room
        rows = await self.db.club_scores(self.club)
        game = P.CLUB_DAY_GAMES * P.CLUB_SCORE["club_game"]
        self.assertEqual(
            [(r["username"], r["score"], r["games"]) for r in rows],
            [
                ("B0_00", game + P.CLUB_SCORE["club_host"], P.CLUB_DAY_GAMES),
                ("B1_00", game, P.CLUB_DAY_GAMES),
            ],
        )
