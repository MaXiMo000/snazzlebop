"""Levels and daily quests over HTTP: your level, today's three quests and claiming a finished one. The
rules are progress.py; XP is earned by the coin and result path in db.py, from fair games only."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import schemas
from .accounts import check_same_origin, session_user
from .config import Settings
from .rooms import HubError

WHY = {
    "not_today": ("not_today", "That isn't one of today's quests", 404),
    "not_done": ("not_done", "Finish the quest first", 409),
    "claimed": ("claimed", "You've already claimed that one", 409),
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

    return api
