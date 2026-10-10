"""Snazzlebop API: app factory, routes, static SPA hosting."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import accounts, calls
from .coins import DAILY_COIN_CAP, season_of
from .config import Settings, load_settings
from .contentgen import ContentGenerator, add_items, claude_caller, known, split_kind
from .db import Database
from .games import catalog
from .logging_setup import setup_logging
from .rooms import Hub, HubError
from .security import (
    BodyLimit,
    HostGuard,
    HttpRateLimit,
    RateLimiter,
    SecurityHeaders,
    client_ip,
)
from .ws import ConnectionCounter, serve_socket

log = logging.getLogger("snazzlebop")

SPA_ROUTE = re.compile(r"(r/[A-Za-z]{3,8}/?|account/?)?")  # "/", "/r/<CODE>", "/account" (App.tsx)


class NameBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    setup_logging(settings.is_production)
    db = Database(settings.database_url)
    background: set[asyncio.Task[None]] = set()

    def record_result(game_id: str, summary: dict[str, Any]) -> None:
        task = asyncio.get_running_loop().create_task(db.record(game_id, summary))
        background.add(task)
        task.add_done_callback(background.discard)

    generator = ContentGenerator(
        claude_caller(settings.anthropic_api_key, settings.content_model)
        if settings.anthropic_api_key
        else None,
        save=db.save_content,
        calls_per_hour=settings.content_calls_per_hour,
    )

    async def pay_coins(rows: list[dict[str, Any]]) -> dict[int, int]:
        return await db.record_results(rows, season_of(), DAILY_COIN_CAP)

    # Wall-clock time (not monotonic) so a room's timers still mean something after a restart.
    hub = Hub(
        settings,
        clock=time.time,
        on_game_finished=record_result,
        on_game_started=generator.request,
        store=db,
        on_results=pay_coins,
        spend_powerup=db.spend_powerup,
        refund_powerup=db.refund_powerup,
    )

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await db.init()
        saved = await db.load_content()  # generated content from earlier runs
        loaded = 0
        for name, payload in saved:
            if known(name):
                kind, theme = split_kind(name)
                loaded += len(add_items(kind, [payload], theme))
        log.info("content: %d saved items loaded; generator %s", loaded, "on" if generator.enabled else "off")
        await db.purge_snapshots(settings.room_max_age_seconds)
        ticker = asyncio.create_task(hub.run_ticker())
        try:
            yield
        finally:
            ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ticker
            await hub.flush()  # live rooms carry on on the next server
            await db.close()

    docs = None if settings.is_production else "/docs"
    app = FastAPI(
        title="Snazzlebop",
        lifespan=lifespan,
        docs_url=docs,
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.hub = hub
    app.state.db = db
    app.state.content = generator
    app.state.ws_counter = ConnectionCounter()

    limiters = {
        "default": RateLimiter(settings.rate_default_per_min / 60, settings.rate_default_burst),
        "create": RateLimiter(settings.rate_create_per_min / 60, settings.rate_create_burst),
        "join": RateLimiter(settings.rate_join_per_min / 60, settings.rate_join_burst),
        "auth": RateLimiter(settings.rate_auth_per_min / 60, settings.rate_auth_burst),
    }
    app.state.limiters = limiters

    # Middleware: the LAST one added is the OUTERMOST. Order at runtime:
    # HostGuard -> SecurityHeaders -> BodyLimit -> HttpRateLimit -> app
    app.add_middleware(
        HttpRateLimit,
        limiters=limiters,
        trusted_hops=settings.trusted_proxy_hops,
        ip_header=settings.client_ip_header,
    )
    app.add_middleware(BodyLimit, max_bytes=settings.max_body_bytes)
    app.add_middleware(
        SecurityHeaders,
        ws_hosts=settings.ws_hosts,
        production=settings.is_production,
        call_hosts=calls.csp_hosts(settings),
    )
    app.add_middleware(HostGuard, allowed_hosts=settings.allowed_hosts, edge_secret=settings.edge_secret)

    # -- error handling: never leak internals or echo input -----------------
    @app.exception_handler(HubError)
    async def hub_error(_: Request, exc: HubError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
        return _error(422, "invalid_request", "That request wasn't valid")

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled error: %s", type(exc).__name__)
        return _error(500, "server_error", "Something went wrong")

    # -- routes --------------------------------------------------------------
    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/games")
    async def games() -> list[dict[str, Any]]:
        return catalog()

    @app.get("/api/stats")
    async def stats() -> dict[str, int]:
        return await db.stats()

    app.include_router(accounts.router(settings, db, limiters["auth"], hub.hosting))

    async def account_id(request: Request) -> int | None:
        user = await accounts.session_user(request, db)
        return user.id if user is not None else None

    @app.post("/api/rooms", status_code=201)
    async def create_room(body: NameBody, request: Request) -> dict[str, str]:
        room, player, token = hub.create_room(body.name, await account_id(request))
        return {"code": room.code, "player_id": player.id, "token": token}

    @app.post("/api/rooms/{code}/join")
    async def join_room(code: str, body: NameBody, request: Request) -> dict[str, str]:
        try:
            await hub.fetch(code.upper())  # back from a restart: restore it first
            room, player, token = hub.join_room(code, body.name, await account_id(request))
        except HubError as exc:
            if exc.code == "room_not_found":
                # Guessing room codes is the main enumeration vector: make it expensive.
                limiters["join"].penalize(
                    client_ip(request.scope, settings.trusted_proxy_hops, settings.client_ip_header), 4
                )
            raise
        return {"code": room.code, "player_id": player.id, "token": token}

    @app.post("/api/rooms/{code}/tv")
    async def tv_seat(code: str, request: Request) -> dict[str, str]:
        """Read-only big-screen view (TV mode). Rate limited and penalised exactly like join."""
        try:
            await hub.fetch(code.upper())
            room, token = hub.issue_tv(code)
        except HubError as exc:
            if exc.code == "room_not_found":
                limiters["join"].penalize(
                    client_ip(request.scope, settings.trusted_proxy_hops, settings.client_ip_header), 4
                )
            raise
        return {"code": room.code, "token": token}

    @app.post("/api/rooms/{code}/audience")
    async def audience_seat(code: str, body: NameBody, request: Request) -> dict[str, str]:
        """A named seat in the crowd (react, predict). Rate limited and penalised exactly like join."""
        try:
            await hub.fetch(code.upper())
            room, watcher, token = hub.join_audience(code, body.name, await account_id(request))
        except HubError as exc:
            if exc.code == "room_not_found":
                limiters["join"].penalize(
                    client_ip(request.scope, settings.trusted_proxy_hops, settings.client_ip_header), 4
                )
            raise
        return {"code": room.code, "player_id": watcher.id, "token": token}

    @app.websocket("/ws/{code}")
    async def ws_route(websocket: WebSocket, code: str) -> None:
        await serve_socket(websocket, code)

    # -- static SPA (same origin => no CORS, strict CSP) ----------------------
    static_root = Path(settings.static_dir).resolve()

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False, response_model=None)
    async def spa(full_path: str) -> FileResponse | JSONResponse:
        if full_path.startswith(("api/", "ws/")) or not static_root.is_dir():
            return _error(404, "not_found", "Not found")
        candidate = (static_root / full_path).resolve()
        if full_path and candidate.is_file() and static_root in candidate.parents:
            immutable = full_path.startswith("assets/")
            cache = "public, max-age=31536000, immutable" if immutable else "no-cache"
            return FileResponse(candidate, headers={"Cache-Control": cache})
        index = static_root / "index.html"
        # Only the SPA's own routes get index.html; anything else (/docs, /admin, typos) is a real 404.
        if index.is_file() and SPA_ROUTE.fullmatch(full_path):
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return _error(404, "not_found", "Not found")

    return app
