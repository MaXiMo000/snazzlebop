"""The inbox, push subscriptions, notification settings, presence as others see it, and room invites.

Presence is only ever shown to friends and clubmates. "Appear offline" hides online and in-game, but
saying you're up for a game is a deliberate signal, so it still shows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import schemas, webpush
from .accounts import check_same_origin, session_user
from .clubs.store import ClubStore
from .config import Settings
from .db import aware
from .notify import KINDS, Notifier, PrefsError, clean_prefs, merged
from .presence import Presence
from .rooms import Hub, HubError

E = schemas.ERRORS


class Statuses:
    """What friends and clubmates see: offline, online, in a game, or up for a game."""

    def __init__(self, db: Any, presence: Presence, hub: Hub) -> None:
        self.db, self.presence, self.hub = db, presence, hub

    async def of(self, user_ids: set[int], club_id: int | None = None) -> dict[int, tuple[str, str | None]]:
        """account -> (status, the game they're up for). `club_id`: count only being up in that club."""
        playing = self.hub.playing(user_ids)
        out: dict[int, tuple[str, str | None]] = {}
        for uid in user_ids:
            up = self.presence.up_of(uid)
            if up is not None and (club_id is None or up.club_id == club_id):
                out[uid] = ("up", up.game)
                continue
            hidden = merged(await self.db.prefs(uid))["hidden"]
            if hidden:
                out[uid] = ("offline", None)
            elif uid in playing:
                out[uid] = ("in_game", None)
            elif self.presence.online(uid):
                out[uid] = ("online", None)
            else:
                out[uid] = ("offline", None)
        return out


class ReadBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    ids: list[int] | None = Field(default=None, max_length=200)  # none: all


class SubscribeBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    endpoint: str = Field(max_length=1000)
    p256dh: str = Field(max_length=120)
    auth: str = Field(max_length=40)


class EndpointBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    endpoint: str = Field(max_length=1000)


class PrefsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hidden: bool | None = None
    types: dict[str, bool] | None = None
    quiet: dict[str, str] | None = None
    tz: int | None = None
    clear_quiet: bool = False  # quiet: null can't be told apart from "not sent"


class InviteBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    username: str = Field(max_length=64)


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, UTC).isoformat()


def router(
    settings: Settings, db: Any, hub: Hub, notifier: Notifier, presence: Presence, statuses: Statuses
) -> APIRouter:
    api = APIRouter()
    clubs = ClubStore(db)

    async def me(request: Request) -> Any:
        if not db.ready:
            raise HubError("accounts_down", "Accounts are unavailable right now. Games still work!", 503)
        user = await session_user(request, db)
        if user is None:
            raise HubError("signed_out", "Sign in first", 401)
        return user

    async def prefs_view(user: Any) -> dict[str, Any]:
        p = merged(await db.prefs(user.id))
        return {
            "hidden": p["hidden"],
            "quiet": p["quiet"],
            "kinds": [{"id": k, "label": v[0], "on": p["types"].get(k, True)} for k, v in KINDS.items()],
            "devices": len(await db.push_subs(user.id)),
        }

    @api.get("/api/notifications", response_model=schemas.Inbox, responses=E)
    async def inbox(request: Request, tz: int | None = None) -> JSONResponse:
        """The inbox, newest first. The app polls this while it's open, which also says you're online
        (and keeps your time zone current for quiet hours)."""
        user = await me(request)
        presence.touch(user.id)
        if tz is not None and -840 <= tz <= 840:
            current = merged(await db.prefs(user.id))
            if current["tz"] != tz:
                await db.save_prefs(user.id, {**current, "tz": tz})
        rows, unread = await db.inbox(user.id)
        items = [
            {
                "id": n.id,
                "kind": n.kind,
                "title": n.title,
                "body": n.body,
                "link": n.link,
                "at": aware(n.created_at).isoformat(),
                "read": n.read_at is not None,
            }
            for n in rows
        ]
        body = {"items": items, "unread": unread, "push_key": notifier.vapid.public_key}
        return JSONResponse(body, headers={"Cache-Control": "no-store"})

    @api.post("/api/notifications/read", response_model=schemas.Ok, responses=E)
    async def read(body: ReadBody, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await me(request)
        await db.mark_read(user.id, body.ids)
        return JSONResponse({"ok": True})

    @api.post("/api/push/subscribe", response_model=schemas.Ok, responses=E)
    async def subscribe(body: SubscribeBody, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await me(request)
        if not webpush.endpoint_ok(body.endpoint) or not webpush.keys_ok(body.p256dh, body.auth):
            raise HubError("bad_subscription", "This browser's push service isn't supported", 400)
        await db.add_push_sub(user.id, body.endpoint, body.p256dh, body.auth)
        return JSONResponse({"ok": True})

    @api.post("/api/push/unsubscribe", response_model=schemas.Ok, responses=E)
    async def unsubscribe(body: EndpointBody, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await me(request)
        await db.delete_push_sub(body.endpoint, user.id)
        return JSONResponse({"ok": True})

    @api.get("/api/me/notify", response_model=schemas.NotifyPrefs, responses=E)
    async def get_prefs(request: Request) -> JSONResponse:
        user = await me(request)
        return JSONResponse(await prefs_view(user), headers={"Cache-Control": "no-store"})

    @api.post("/api/me/notify", response_model=schemas.NotifyPrefs, responses=E)
    async def set_prefs(body: PrefsBody, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await me(request)
        update = body.model_dump(exclude_none=True, exclude={"clear_quiet"})
        if body.clear_quiet:
            update["quiet"] = None
        try:
            await db.save_prefs(user.id, clean_prefs(update, await db.prefs(user.id)))
        except PrefsError as exc:
            raise HubError("bad_input", str(exc)) from None
        return JSONResponse(await prefs_view(user))

    # -- inviting people to a room ----------------------------------------------------------------------
    async def invitees(user: Any, room: Any) -> list[tuple[int, str, str]]:
        """(id, username, why) of the people you may invite: mutual friends, and clubmates in a club room.
        Anyone already seated is left out."""
        people: dict[int, tuple[str, str]] = {}
        if room.club_id is not None:
            for m in await clubs.members(room.club_id):
                people[m.user_id] = (m.username, "club")
        for uid, name in (await db.friends(user.id))["mutual"]:
            people[uid] = (name, "friend")
        seated = {uid for pid, uid in room.accounts.items() if pid in room.players}
        return [(uid, n, why) for uid, (n, why) in people.items() if uid != user.id and uid not in seated]

    @api.get("/api/rooms/{code}/invitees", response_model=schemas.Invitees, responses=E)
    async def list_invitees(code: str, request: Request) -> JSONResponse:
        user = await me(request)
        room = hub.seated(code, user.id)
        if room is None:
            raise HubError("not_in_room", "Join the room first", 403)
        found = await invitees(user, room)
        status = await statuses.of({uid for uid, _, _ in found})
        order = {"up": 0, "online": 1, "in_game": 2, "offline": 3}
        people = sorted(
            ({"username": n, "status": status[uid][0], "why": why} for uid, n, why in found),
            key=lambda p: (order[p["status"]], p["username"].casefold()),
        )
        return JSONResponse({"people": people[:60]}, headers={"Cache-Control": "no-store"})

    @api.post("/api/rooms/{code}/invite", response_model=schemas.Ok, responses=E)
    async def invite(code: str, body: InviteBody, request: Request) -> JSONResponse:
        """Tell a friend or clubmate you're in a room. They get it in their inbox (and as a push)."""
        check_same_origin(request, settings)
        user = await me(request)
        room = hub.seated(code, user.id)
        if room is None:
            raise HubError("not_in_room", "Join the room first", 403)
        wanted = body.username.strip().casefold()
        target = next((t for t in await invitees(user, room) if t[1].casefold() == wanted), None)
        if target is None:
            raise HubError("cant_invite", "You can invite friends (who added you back) and clubmates", 403)
        club = None
        title = f"{user.username} invites you to play"
        if room.club_id is not None:
            info = await clubs.by_id(room.club_id)
            if info is not None:
                club = (info.id, (info.rules or {}).get("quiet"))
                title = f"{user.username} invites you to play ({info.name})"
        await notifier.notify(
            [target[0]],
            "invite",
            title,
            f"Room {room.code} is open. Tap to jump in.",
            f"/r/{room.code}",
            group=f"invite:{room.code}",
            club=club,
        )
        return JSONResponse({"ok": True})  # the same answer whatever their settings: nothing leaks

    return api
