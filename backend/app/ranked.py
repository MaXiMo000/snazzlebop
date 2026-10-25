"""Ranked play over HTTP: your ratings, the leaderboards (everyone, a club, a place; this season or
this week) and whether you appear on place boards. The model is ratings.py; games are rated by the hub
from the server's final scores (rooms/flow.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from . import ratings as ratinglib
from . import schemas
from .accounts import check_same_origin, session_user
from .clubs.store import ClubStore
from .config import Settings
from .db import aware
from .games import REGISTRY
from .games.catalogue import RANKED
from .rooms import HubError

SCOPES = ("everyone", "club", "place")
PERIODS = ("season", "week")


class PlaceBoardsBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    on: bool


def season_view() -> dict[str, Any]:
    n = ratinglib.season_of()
    start, end = ratinglib.season_dates(n)
    return {"number": n, "starts": start.isoformat(), "ends": end.isoformat()}


def router(settings: Settings, db: Any) -> APIRouter:
    api = APIRouter()
    clubs = ClubStore(db)

    async def me(request: Request) -> Any:
        if not db.ready:
            raise HubError("accounts_down", "Accounts are unavailable right now. Games still work!", 503)
        user = await session_user(request, db)
        if user is None:
            raise HubError("signed_out", "Sign in first", 401)
        return user

    @api.get("/api/ratings/me", response_model=schemas.MyRatings, responses=schemas.ERRORS)
    async def my_ratings(request: Request) -> JSONResponse:
        user = await me(request)
        have = {r["game"]: r for r in await db.my_ratings(user.id)}
        games = []
        for game_id in sorted(RANKED, key=lambda g: REGISTRY[g].title):
            r = have.get(game_id, {"rating": ratinglib.Rating().display, "games": 0})
            games.append(
                {
                    "game": game_id,
                    "title": REGISTRY[game_id].title,
                    "rating": r["rating"],
                    "games": r["games"],
                    "tier": ratinglib.tier(r["rating"], r["games"]),
                    "placement_left": max(0, ratinglib.PROVISIONAL_GAMES - r["games"]),
                }
            )
        body = {"season": season_view(), "games": games, "place_boards": bool(user.place_boards)}
        return JSONResponse(body, headers={"Cache-Control": "no-store"})

    @api.get("/api/ratings/board", response_model=schemas.RatingBoard, responses=schemas.ERRORS)
    async def board(
        request: Request, game: str, scope: str = "everyone", slug: str = "", period: str = "season"
    ) -> JSONResponse:
        user = await me(request)
        if game not in RANKED or scope not in SCOPES or period not in PERIODS:
            raise HubError("bad_board", "Unknown leaderboard", 404)
        among: set[int] | None = None
        if scope == "club":
            club = await clubs.by_slug(slug)
            mine = await clubs.membership(club.id, user.id) if club is not None else None
            if club is None or mine is None or mine.banned:
                raise HubError("not_found", "Club not found", 404)
            among = await db.club_member_ids(club.id)
        elif scope == "place":
            place = await db.place_by_slug(slug) if isinstance(slug, str) and len(slug) <= 48 else None
            here = (await db.user_places([user.id])).get(user.id, []) if place is not None else []
            if place is None or not any(
                p.id == place.id and aware(exp) > datetime.now(UTC) for p, _, exp in here
            ):
                raise HubError("not_found", "Place not found", 404)
            among = await db.place_board_ids(place.id)
        rows = await db.rating_board(game, among, week=period == "week")
        body = {
            "game": game,
            "title": REGISTRY[game].title,
            "scope": scope,
            "period": period,
            "season": season_view(),
            "rows": [{**r, "you": r["username"] == user.username} for r in rows],
        }
        return JSONResponse(body, headers={"Cache-Control": "no-store"})

    @api.post("/api/me/place-boards", response_model=schemas.Ok, responses=schemas.ERRORS)
    async def place_boards(body: PlaceBoardsBody, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await me(request)
        await db.set_place_boards(user.id, body.on)
        return JSONResponse({"ok": True})

    return api
