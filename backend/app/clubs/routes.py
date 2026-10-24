"""The clubs API. Every route needs a signed-in account and changes need the same-origin check (the
middleware's per-address limit covers them); redeeming an invite also spends the sign-in budget, so
codes can't be guessed in bulk. A club is invisible to non-members (404, so names can't be probed);
the way in is an invite link from a member.

"Up for a game" lives here too: members say they're free, and once enough are (presence.py) the
others are told (notify.py) and the first to tap through opens the room."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .. import schemas
from ..accounts import check_same_origin, session_user
from ..config import Settings
from ..db import Club, ClubInvite, Database, aware
from ..games import REGISTRY
from ..notifications import Statuses, iso
from ..notify import Notifier, merged
from ..presence import MATCH_AT, UP_MINUTES, Presence
from ..rooms import Hub, HubError
from ..security import RateLimiter, client_ip
from . import policy
from .policy import PolicyError
from .store import ClubStore

E = schemas.ERRORS


class NewClubBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(max_length=80)
    about: str | None = Field(default=None, max_length=400)
    rules: dict[str, Any] | None = None


class SettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str | None = Field(default=None, max_length=80)
    about: str | None = Field(default=None, max_length=400)
    rules: dict[str, Any] | None = None


class InviteBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    days: int | None = None
    uses: int | None = None


class CodeBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    code: str = Field(max_length=32)


class RoleBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    role: str = Field(max_length=12)


class RemoveBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    ban: bool = False


class HandOverBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    username: str = Field(max_length=64)


class RoomBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=64)


class UpBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    game: str | None = Field(default=None, max_length=32)  # None: any game
    minutes: int = 60


class MuteBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    muted: bool


def router(
    settings: Settings,
    db: Database,
    hub: Hub,
    limiter: RateLimiter,
    notifier: Notifier,
    presence: Presence,
    statuses: Statuses,
) -> APIRouter:
    api = APIRouter()
    store = ClubStore(db)

    async def me(request: Request) -> Any:
        if not db.ready:
            raise HubError("accounts_down", "Clubs are unavailable right now. Games still work!", 503)
        user = await session_user(request, db)
        if user is None:
            raise HubError("signed_out", "Sign in first", 401)
        return user

    def write(request: Request) -> None:
        check_same_origin(request, settings)

    async def club_and_role(slug: str, user: Any) -> tuple[Club, str]:
        """The club and your role in it; 404 for anyone who isn't a member (or was banned)."""
        club = await store.by_slug(slug)
        member = await store.membership(club.id, user.id) if club is not None else None
        if club is None or member is None or member.banned:
            raise HubError("no_club", "Club not found", 404)
        return club, member.role

    def invite_info(i: ClubInvite) -> dict[str, Any]:
        return {"id": i.id, "uses_left": i.uses_left, "expires_at": aware(i.expires_at).isoformat()}

    def up_view(club: Club, user: Any) -> dict[str, Any]:
        mine = presence.up_of(user.id)
        match = presence.match_for(club.id)
        return {
            "mine": {"game": mine.game, "until": iso(mine.until)}
            if mine and mine.club_id == club.id
            else None,
            "count": len(presence.club_ups(club.id)),
            "needed": MATCH_AT,
            "match": {
                "game": match.game,
                "players": len(match.members),
                "room": match.room if match.room and hub.get(match.room) else None,
                "mine": user.id in match.members,
            }
            if match
            else None,
        }

    async def detail(club: Club, role: str, user: Any) -> dict[str, Any]:
        members = await store.members(club.id)
        status = await statuses.of({m.user_id for m in members}, club.id, viewer=user.id)
        muted = club.id in merged(await db.prefs(user.id))["muted_clubs"]
        now = datetime.now(UTC)
        badges = {
            uid: [p.name for p, _, until in rows if until > now]
            for uid, rows in (await db.user_places([m.user_id for m in members])).items()
        }
        place = await required_place(club)
        return {
            "slug": club.slug,
            "name": club.name,
            "about": club.about,
            "rules": policy.clean_rules(club.rules or None),
            "role": role,
            "member_count": len(members),
            "members": [
                {
                    "username": m.username,
                    "role": m.role,
                    "joined_at": aware(m.joined_at).isoformat(),
                    "status": status[m.user_id][0],
                    "up_game": status[m.user_id][1],
                    "places": badges.get(m.user_id, []),
                }
                for m in members
            ],
            "rooms": hub.club_rooms(club.id),
            "invites": [invite_info(i) for i in await store.invites(club.id)]
            if policy.may_invite(role)
            else [],
            "up": up_view(club, user),
            "place": {"slug": place.slug, "name": place.name} if place is not None else None,
            "muted": muted,
            "open_reports": await db.open_reports(club.id) if policy.may_invite(role) else 0,
        }

    async def required_place(club: Club) -> Any:
        slug = policy.clean_rules(club.rules or None)["place"]
        return await db.place_by_slug(slug) if slug else None

    async def require_place(club: Club, user: Any) -> None:
        """A club for one place lets in only people verified there now (members already in stay)."""
        place = await required_place(club)
        if place is None or await store.membership(club.id, user.id) is not None:
            return
        mine = (await db.user_places([user.id])).get(user.id, [])
        if not any(p.id == place.id and until > datetime.now(UTC) for p, _, until in mine):
            raise HubError(
                "place_required",
                f"This club is for people verified at {place.name}. Verify it on your Places page first",
                403,
            )

    async def check_place_rule(rules: dict[str, Any]) -> None:
        if rules.get("place") and await db.place_by_slug(rules["place"]) is None:
            raise HubError("bad_input", "Pick a place from the list")

    def fail(exc: PolicyError) -> HubError:
        return HubError(exc.code, exc.message, exc.status)

    async def target(club: Club, username: str) -> tuple[int, str]:
        """(user id, role) of a member named in a request; 404 if they aren't in the club."""
        for m in await store.members(club.id):
            if m.username.casefold() == username.strip().casefold():
                return m.user_id, m.role
        raise HubError("no_member", "That person isn't in this club", 404)

    @api.get("/api/clubs", response_model=schemas.ClubList, responses=E)
    async def my_clubs(request: Request) -> JSONResponse:
        user = await me(request)
        rows = await store.mine(user.id)
        clubs = [
            {"slug": c.slug, "name": c.name, "about": c.about, "role": r, "members": n} for c, r, n in rows
        ]
        return JSONResponse({"clubs": clubs}, headers={"Cache-Control": "no-store"})

    @api.post("/api/clubs", status_code=201, response_model=schemas.ClubDetail, responses=E)
    async def create(body: NewClubBody, request: Request) -> JSONResponse:
        write(request)
        user = await me(request)
        try:
            name, about = policy.clean_name(body.name), policy.clean_about(body.about)
            rules = policy.clean_rules(body.rules)
            await check_place_rule(rules)
            if await store.count_owned(user.id) >= policy.MAX_OWNED:
                raise PolicyError("too_many_clubs", f"You can own up to {policy.MAX_OWNED} clubs", 409)
            club = await store.create(user.id, name, about, rules)
        except PolicyError as exc:
            raise fail(exc) from None
        return JSONResponse(await detail(club, "owner", user), status_code=201)

    @api.get("/api/clubs/{slug}", response_model=schemas.ClubDetail, responses=E)
    async def show(slug: str, request: Request) -> JSONResponse:
        user = await me(request)
        club, role = await club_and_role(slug, user)
        return JSONResponse(await detail(club, role, user), headers={"Cache-Control": "no-store"})

    @api.post("/api/clubs/{slug}/settings", response_model=schemas.ClubDetail, responses=E)
    async def change_settings(slug: str, body: SettingsBody, request: Request) -> JSONResponse:
        write(request)
        user = await me(request)
        club, role = await club_and_role(slug, user)
        if not policy.may_edit(role):
            raise HubError("not_allowed", "Only the club's owner and admins can change that", 403)
        values: dict[str, Any] = {}
        try:
            if body.name is not None:
                values["name"] = policy.clean_name(body.name)
            if body.about is not None:
                values["about"] = policy.clean_about(body.about)
            if body.rules is not None:
                values["rules"] = policy.clean_rules(body.rules)
                await check_place_rule(values["rules"])
        except PolicyError as exc:
            raise fail(exc) from None
        if values:
            await store.update(club.id, values)
        club, role = await club_and_role(slug, user)
        return JSONResponse(await detail(club, role, user))

    @api.post("/api/clubs/{slug}/invites", status_code=201, response_model=schemas.NewInvite, responses=E)
    async def invite(slug: str, body: InviteBody, request: Request) -> JSONResponse:
        write(request)
        user = await me(request)
        club, role = await club_and_role(slug, user)
        if not policy.may_invite(role):
            raise HubError("not_allowed", "Only moderators and up can make invite links", 403)
        try:
            days = policy.clamp(body.days, policy.INVITE_DAYS, 7, "Days")
            uses = policy.clamp(body.uses, policy.INVITE_USES, 25, "Uses")
        except PolicyError as exc:
            raise fail(exc) from None
        code = policy.new_invite_code()
        made = await store.add_invite(
            club.id, user.id, policy.hash_invite(settings.secret_key, code), uses, days
        )
        body_out = {**invite_info(made), "code": code, "path": f"/join/{code}"}
        return JSONResponse(body_out, status_code=201, headers={"Cache-Control": "no-store"})

    @api.post("/api/clubs/{slug}/invites/{invite_id}/revoke", response_model=schemas.Ok, responses=E)
    async def revoke(slug: str, invite_id: int, request: Request) -> JSONResponse:
        write(request)
        user = await me(request)
        club, role = await club_and_role(slug, user)
        if not policy.may_invite(role):
            raise HubError("not_allowed", "Only moderators and up can manage invite links", 403)
        if not await store.revoke_invite(club.id, invite_id):
            raise HubError("no_invite", "That invite link is already gone", 404)
        return JSONResponse({"ok": True})

    @api.post("/api/clubs/join", response_model=schemas.ClubDetail, responses=E)
    async def join(body: CodeBody, request: Request) -> JSONResponse:
        write(request)
        if not limiter.allow(
            client_ip(request.scope, settings.trusted_proxy_hops, settings.client_ip_header)
        ):
            raise HubError("rate_limited", "Too many tries. Wait a minute and try again", 429)
        user = await me(request)
        code_hash = policy.hash_invite(settings.secret_key, body.code)
        target = await store.club_for_invite(code_hash)
        if target is not None:
            await require_place(target, user)
        try:
            club = await store.redeem(code_hash, user.id)
        except PolicyError as exc:
            raise fail(exc) from None
        club, role = await club_and_role(club.slug, user)
        return JSONResponse(await detail(club, role, user))

    @api.post("/api/clubs/{slug}/members/{username}", response_model=schemas.Ok, responses=E)
    async def set_role(slug: str, username: str, body: RoleBody, request: Request) -> JSONResponse:
        write(request)
        user = await me(request)
        club, role = await club_and_role(slug, user)
        uid, current = await target(club, username)
        if uid == user.id or not policy.may_set_role(role, current, body.role):
            raise HubError("not_allowed", "You can't give that role", 403)
        await store.set_role(club.id, uid, body.role)
        return JSONResponse({"ok": True})

    @api.post("/api/clubs/{slug}/members/{username}/remove", response_model=schemas.Ok, responses=E)
    async def remove(slug: str, username: str, body: RemoveBody, request: Request) -> JSONResponse:
        write(request)
        user = await me(request)
        club, role = await club_and_role(slug, user)
        uid, current = await target(club, username)
        if uid == user.id or not policy.may_remove(role, current):
            raise HubError("not_allowed", "You can't remove that person", 403)
        await store.remove(club.id, uid, body.ban)
        presence.leave_club(club.id, uid)
        return JSONResponse({"ok": True})

    @api.post("/api/clubs/{slug}/transfer", response_model=schemas.Ok, responses=E)
    async def transfer(slug: str, body: HandOverBody, request: Request) -> JSONResponse:
        write(request)
        user = await me(request)
        club, role = await club_and_role(slug, user)
        if role != "owner":
            raise HubError("not_allowed", "Only the owner can hand the club over", 403)
        uid, _ = await target(club, body.username)
        if uid == user.id:
            raise HubError("bad_target", "Hand the club to someone else", 400)
        try:
            await store.transfer(club.id, user.id, uid)
        except PolicyError as exc:
            raise fail(exc) from None
        return JSONResponse({"ok": True})

    @api.post("/api/clubs/{slug}/leave", response_model=schemas.Ok, responses=E)
    async def leave(slug: str, request: Request) -> JSONResponse:
        """Members leave freely. The owner hands the club over first, unless they're the last one in
        (then the club closes)."""
        write(request)
        user = await me(request)
        club, role = await club_and_role(slug, user)
        if role == "owner":
            if len(await store.members(club.id)) > 1:
                raise HubError("owner_leaving", "Hand the club to someone before you leave", 409)
            await store.delete(club.id)
            presence.forget_club(club.id)
        else:
            await store.remove(club.id, user.id, ban=False)
            presence.leave_club(club.id, user.id)
        return JSONResponse({"ok": True})

    @api.post("/api/clubs/{slug}/delete", response_model=schemas.Ok, responses=E)
    async def delete_club(slug: str, request: Request) -> JSONResponse:
        write(request)
        user = await me(request)
        club, role = await club_and_role(slug, user)
        if role != "owner":
            raise HubError("not_allowed", "Only the owner can close the club", 403)
        await store.delete(club.id)
        presence.forget_club(club.id)
        return JSONResponse({"ok": True})

    @api.post("/api/clubs/{slug}/rooms", status_code=201, response_model=schemas.RoomPass, responses=E)
    async def club_room(slug: str, body: RoomBody, request: Request) -> JSONResponse:
        """Open a room for the club: its members see it on the club page and can walk in."""
        write(request)
        user = await me(request)
        club, _ = await club_and_role(slug, user)
        rules = policy.clean_rules(club.rules or None)
        circle = await db.circle(user.id)
        mutes = {u: t.timestamp() for u, t in (await db.club_mutes(club.id)).items()}
        room, player, token = hub.create_room(
            body.name, user.id, circle, club_id=club.id, club_rules=rules, club_muted=mutes
        )
        hub.set_hidden(user.id, await db.block_set(user.id))
        return JSONResponse({"code": room.code, "player_id": player.id, "token": token}, status_code=201)

    # -- up for a game ----------------------------------------------------------------------------------
    async def tell_club(club: Club, match: Any) -> None:
        """Enough people are up: tell the club (each person's settings, limits and quiet hours apply)."""
        members = await store.members(club.id)
        game = REGISTRY[match.game].title if match.game in REGISTRY else "a game"
        title = f"Game on in {club.name}!"
        body = f"{len(match.members)} people want to play {game}. Tap to join them."
        rules = policy.clean_rules(club.rules or None)
        told = await notifier.notify(
            [m.user_id for m in members],
            "club_up",
            title,
            body,
            f"/clubs/{club.slug}",
            group=f"club_up:{club.id}:{match.id}",
            club=(club.id, rules["quiet"]),
        )
        match.told.update(told)

    @api.post("/api/clubs/{slug}/up", response_model=schemas.ClubDetail, responses=E)
    async def up(slug: str, body: UpBody, request: Request) -> JSONResponse:
        """Say you're up for a game (any, or one pick) for 30, 60 or 120 minutes."""
        write(request)
        user = await me(request)
        club, role = await club_and_role(slug, user)
        if body.minutes not in UP_MINUTES:
            raise HubError("bad_input", "Pick 30, 60 or 120 minutes")
        allowed = policy.clean_rules(club.rules or None)["games"]
        if body.game is not None and (body.game not in REGISTRY or (allowed and body.game not in allowed)):
            raise HubError("bad_game", "Pick one of the club's games")
        match = presence.up(user.id, club.id, body.game, body.minutes)
        if match is not None:
            await tell_club(club, match)
        return JSONResponse(await detail(club, role, user))

    @api.post("/api/clubs/{slug}/up/cancel", response_model=schemas.ClubDetail, responses=E)
    async def down(slug: str, request: Request) -> JSONResponse:
        write(request)
        user = await me(request)
        club, role = await club_and_role(slug, user)
        presence.down(user.id)
        return JSONResponse(await detail(club, role, user))

    @api.post("/api/clubs/{slug}/up/go", status_code=201, response_model=schemas.RoomPass, responses=E)
    async def go(slug: str, body: RoomBody, request: Request) -> JSONResponse:
        """Tap through to the match: the first one in opens the room and hosts it, the rest join it.
        Club members who weren't up can join too, as long as there's a seat."""
        write(request)
        user = await me(request)
        club, _ = await club_and_role(slug, user)
        match = presence.match_for(club.id)
        if match is None:
            raise HubError("no_match", "That game isn't on any more. Say you're up to start another", 404)
        circle = await db.circle(user.id)  # before any check-then-act below: no await in between
        room = hub.get(match.room) if match.room else None
        blocks = await db.block_set(user.id)
        if room is not None and room.accounts.get(room.host_id) in blocks:
            raise HubError("cant_join", "You can't join this room", 403)
        mutes = {u: t.timestamp() for u, t in (await db.club_mutes(club.id)).items()}
        if room is None:
            rules = policy.clean_rules(club.rules or None)
            room, player, token = hub.create_room(
                body.name, user.id, circle, club_id=club.id, club_rules=rules, club_muted=mutes
            )
            match.room = room.code
        else:
            room, player, token = hub.join_room(room.code, body.name, user.id)
        hub.set_hidden(user.id, blocks)
        if user.id not in match.members:
            match.members.append(user.id)
        presence.down(user.id)  # playing now: the signal has done its job
        return JSONResponse({"code": room.code, "player_id": player.id, "token": token}, status_code=201)

    @api.post("/api/clubs/{slug}/mute", response_model=schemas.Ok, responses=E)
    async def mute(slug: str, body: MuteBody, request: Request) -> JSONResponse:
        """Stop (or restart) hearing about games filling up in this club."""
        write(request)
        user = await me(request)
        club, _ = await club_and_role(slug, user)
        prefs = merged(await db.prefs(user.id))
        muted = [c for c in prefs["muted_clubs"] if c != club.id]
        if body.muted:
            muted.append(club.id)
        await db.save_prefs(user.id, {**prefs, "muted_clubs": muted[-100:]})
        return JSONResponse({"ok": True})

    return api
