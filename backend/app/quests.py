"""Levels and daily quests over HTTP: your level, today's three quests and claiming a finished one. The
rules are progress.py; XP is earned by the coin and result path in db.py, from fair games only."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import billing, progress, schemas
from .accounts import check_same_origin, session_user
from .config import Settings
from .rooms import HubError

WHY = {
    "not_today": ("not_today", "That isn't one of today's quests", 404),
    "not_done": ("not_done", "Finish the quest first", 409),
    "claimed": ("claimed", "You've already claimed that one", 409),
    "rerolled": ("rerolled", "You've used today's reroll", 409),
}


class LookBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame: str = Field(max_length=16)
    win: str = Field(max_length=16)


def _look(user: Any) -> dict[str, Any]:
    level = progress.level_of(user.xp or 0)
    plus = billing.has_plus(user)
    return {
        "level": level,
        "plus": plus,
        "slots": progress.power_slots(level, plus),
        "slot_level": progress.SLOT_LEVEL,
        **progress.clean_look(user.look, level, plus),
        **progress.look_options(level, plus),
    }


def router(settings: Settings, db: Any) -> APIRouter:
    api = APIRouter()

    async def me(request: Request) -> Any:
        if not db.ready:
            raise HubError("accounts_down", "Accounts are unavailable right now. Games still work!", 503)
        user = await session_user(request, db)
        if user is None:
            raise HubError("signed_out", "Sign in first", 401)
        return user

    @api.get("/api/me/look", response_model=schemas.MyLook, responses=schemas.ERRORS)
    async def my_look(request: Request) -> JSONResponse:
        """Your unlocks: the avatar frames and victory animations open to your level, and your picks."""
        user = await me(request)
        return JSONResponse(_look(user), headers={"Cache-Control": "no-store"})

    @api.post("/api/me/look", response_model=schemas.MyLook, responses=schemas.ERRORS)
    async def set_look(body: LookBody, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await me(request)
        level, plus = progress.level_of(user.xp or 0), billing.has_plus(user)
        for pick, table in ((body.frame, progress.FRAMES), (body.win, progress.WINS)):
            if pick not in table:
                raise HubError("bad_look", "That isn't one of the looks", 400)
            if not progress.unlocked(table[pick][1], level, plus):
                raise HubError("locked", "Unlock that one first", 403)
        await db.set_look(user.id, {"frame": body.frame, "win": body.win})
        user.look = {"frame": body.frame, "win": body.win}
        return JSONResponse(_look(user), headers={"Cache-Control": "no-store"})

    @api.get("/api/me/progress", response_model=schemas.Progress, responses=schemas.ERRORS)
    async def my_progress(request: Request) -> JSONResponse:
        user = await me(request)
        return JSONResponse(await db.progress(user.id), headers={"Cache-Control": "no-store"})

    @api.post("/api/me/quests/{quest}/claim", response_model=schemas.Progress, responses=schemas.ERRORS)
    async def claim(quest: str, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await me(request)
        why = await db.claim_quest(user.id, quest[:32])
        if why:
            raise HubError(*WHY[why])
        return JSONResponse(await db.progress(user.id), headers={"Cache-Control": "no-store"})

    @api.post("/api/me/quests/{quest}/reroll", response_model=schemas.Progress, responses=schemas.ERRORS)
    async def reroll(quest: str, request: Request) -> JSONResponse:
        """Swap one of today's quests for another of its kind (once a day, not after claiming it)."""
        check_same_origin(request, settings)
        user = await me(request)
        why = await db.reroll_quest(user.id, quest[:32])
        if why:
            raise HubError(*WHY[why])
        return JSONResponse(await db.progress(user.id), headers={"Cache-Control": "no-store"})

    @api.post("/api/me/season/{challenge}/claim", response_model=schemas.Progress, responses=schemas.ERRORS)
    async def claim_season(challenge: str, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await me(request)
        why = await db.claim_season(user.id, challenge[:32])
        if why:
            raise HubError(*WHY[why])
        return JSONResponse(await db.progress(user.id), headers={"Cache-Control": "no-store"})

    @api.post("/api/me/weekly/{challenge}/claim", response_model=schemas.Progress, responses=schemas.ERRORS)
    async def claim_weekly(challenge: str, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await me(request)
        why = await db.claim_weekly(user.id, challenge[:32])
        if why:
            raise HubError(*WHY[why])
        return JSONResponse(await db.progress(user.id), headers={"Cache-Control": "no-store"})

    return api
