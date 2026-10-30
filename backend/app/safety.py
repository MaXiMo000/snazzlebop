"""Safety: blocking, reporting, the club moderators' queue, and your data.

- Block: silent to the blocked person. Neither of you can add, invite or see the other's presence, the
  blocked person can't join rooms you host, and in a shared room neither sees the other's chat.
- Report: a person (from a club's member list) or a seat in a room. The context (their recent chat
  lines) is captured by the server, never typed by the reporter. Reports in a club, or about someone
  in a club room, go to that club's moderators; the rest wait for platform staff.
- Moderators (and up) work the queue: dismiss, mute in the club's rooms, remove, ban, or escalate to
  staff. They act only on people below their own role, and every action is written to the audit log.
- Every report is a case (events.py): a public id, a priority, a timeline, and events delivered to other
  systems through the outbox (a signed webhook today), so triage by a model or tickets in Jira can be
  added without changing this code. Those systems write back through integrations.py.
- Your data: download everything kept about your account.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from . import events, schemas
from .accounts import USERNAME_RE, check_same_origin, session_user
from .clubs import policy
from .clubs.store import ClubStore
from .config import Settings
from .db import aware
from .outbox import Outbox
from .presence import Presence
from .rooms import Hub, HubError

E = schemas.ERRORS
REASONS = events.REASONS
REPORTS_PER_DAY = 20
MUTE_HOURS = (1, 24, 168)
ACTIONS = ("dismiss", "mute", "remove", "ban", "escalate")


class PersonBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    username: str = Field(max_length=64)


class ReportBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    username: str = Field(max_length=64)
    reason: str = Field(max_length=16)
    note: str = Field(default="", max_length=500)
    club: str | None = Field(default=None, max_length=48)  # the club it happened in


class SeatReportBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    player_id: str = Field(max_length=32)
    reason: str = Field(max_length=16)
    note: str = Field(default="", max_length=500)
    block: bool = False


class SeatBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    player_id: str = Field(max_length=32)


class ActBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: str = Field(max_length=12)
    hours: int | None = None  # for "mute"


def clean_note(raw: str) -> str:
    return " ".join("".join(ch for ch in raw if ch.isprintable()).split())[:500]


def written(d: dict[str, Any]) -> str:
    """What an integration changed, in words: "Triage: hate (93%); priority urgent; status triaged"."""
    parts = []
    if d.get("label"):
        score = d.get("score")
        parts.append(f"Triage: {d['label']}" + (f" ({score:.0%})" if isinstance(score, float) else ""))
    parts += [f"Linked {k} {v.get('key', '')}" for k, v in (d.get("external") or {}).items()]
    parts += [f"{k} {d[k]}" for k in ("priority", "status", "assignee") if d.get(k)]
    return "; ".join(parts) or "Updated"


def history(event: Any) -> dict[str, str]:
    """One timeline entry, in words a moderator reads at a glance."""
    who = event.actor.split(":", 1)
    actor = f"{who[1]} ({who[0]})" if who[0] in ("integration", "staff") else who[-1]
    d = event.data or {}
    text = {
        "created": "Reported",
        "merged": "Reported again" + (f" ({d['lines']} more chat lines)" if d.get("lines") else ""),
        "action": {
            "mute": f"Muted for {d.get('hours')} h",
            "remove": "Removed from the club",
            "ban": "Banned from the club",
            "dismiss": "Dismissed",
            "escalate": "Sent to staff",
            "suspend": "Account suspended "
            + ("for good" if d.get("days") == 0 else f"for {d.get('days')} days"),
            "return": "Handed back to the club",
        }.get(d.get("action", ""), str(d.get("action", ""))),
        "triage": written(d),
        "external": written(d),
        "status": written(d),
        "update": written(d),
    }.get(event.kind, event.kind)
    if d.get("note") and event.kind in ("status", "update", "triage", "action"):
        text += f": {d['note']}"
    return {"at": aware(event.created_at).isoformat(), "actor": actor, "text": text}


def case_view(r: Any) -> dict[str, Any]:
    """The case fields the moderators' page shows next to the report itself."""
    triage = dict(r.triage or {})
    return {
        "public_id": r.public_id,
        "priority": r.priority,
        "triage": {
            "label": str(triage.get("label", "")),
            "score": triage.get("score"),
            "summary": str(triage.get("summary", "")),
            "by": str(triage.get("by", "")),
        }
        if triage
        else None,
        "tickets": [
            {"system": k, "key": str(v.get("key", "")), "url": v.get("url")}
            for k, v in (r.external or {}).items()
            if isinstance(v, dict)
        ],
    }


def router(settings: Settings, db: Any, hub: Hub, presence: Presence, outbox: Outbox) -> APIRouter:
    api = APIRouter()
    clubs = ClubStore(db)

    def payload(report: Any, club: Any) -> dict[str, Any]:
        return events.report_payload(report, club, settings.site, settings.secret_key)

    def actor(user: Any) -> str:
        return f"user:{user.username}"

    async def me(request: Request) -> Any:
        if not db.ready:
            raise HubError("accounts_down", "Accounts are unavailable right now. Games still work!", 503)
        user = await session_user(request, db)
        if user is None:
            raise HubError("signed_out", "Sign in first", 401)
        return user

    async def person(username: str) -> Any:
        name = username.strip()
        other = await db.user_by_name(name) if USERNAME_RE.fullmatch(name) else None
        if other is None:
            raise HubError("no_such_user", "No account with that username", 404)
        return other

    async def refresh_rooms(*user_ids: int) -> None:
        for uid in user_ids:
            hub.set_hidden(uid, await db.block_set(uid))

    def reason_ok(reason: str) -> None:
        if reason not in REASONS:
            raise HubError("bad_input", "Pick a reason")

    async def under_limit(user: Any) -> None:
        if await db.reports_today(user.id) >= REPORTS_PER_DAY:
            raise HubError(
                "too_many_reports", "That's a lot of reports today. Our team will look at them", 429
            )

    # -- blocking -----------------------------------------------------------------------------------------
    @api.get("/api/blocks", response_model=schemas.BlockList, responses=E)
    async def blocked(request: Request) -> JSONResponse:
        user = await me(request)
        people = [
            {"username": n, "since": aware(at).isoformat()} for n, at in await db.blocked_by_me(user.id)
        ]
        return JSONResponse({"people": people}, headers={"Cache-Control": "no-store"})

    async def do_block(user: Any, other_id: int) -> None:
        if other_id == user.id:
            raise HubError("bad_target", "That's you!")
        await db.block(user.id, other_id)
        await refresh_rooms(user.id, other_id)

    @api.post("/api/blocks", response_model=schemas.Ok, responses=E)
    async def block(body: PersonBody, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await me(request)
        await do_block(user, (await person(body.username)).id)
        return JSONResponse({"ok": True})

    @api.post("/api/blocks/remove", response_model=schemas.Ok, responses=E)
    async def unblock(body: PersonBody, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await me(request)
        other = await person(body.username)
        await db.unblock(user.id, other.id)
        await refresh_rooms(user.id, other.id)
        return JSONResponse({"ok": True})

    @api.post("/api/rooms/{code}/block", response_model=schemas.Ok, responses=E)
    async def block_seat(code: str, body: SeatBody, request: Request) -> JSONResponse:
        """Block someone you're in a room with (by their seat: accounts aren't shown in rooms)."""
        check_same_origin(request, settings)
        user = await me(request)
        if hub.seated(code, user.id) is None:
            raise HubError("not_in_room", "Join the room first", 403)
        seat = hub.seat_of(code, body.player_id)
        if seat is None or seat[2] is None:
            raise HubError(
                "no_account", "Only signed-in players can be blocked. The host can remove guests", 400
            )
        await do_block(user, seat[2])
        return JSONResponse({"ok": True})

    # -- reporting ----------------------------------------------------------------------------------------
    @api.post("/api/reports", response_model=schemas.Ok, responses=E)
    async def report(body: ReportBody, request: Request) -> JSONResponse:
        """Report a person, optionally in a club you share (then its moderators see it)."""
        check_same_origin(request, settings)
        user = await me(request)
        reason_ok(body.reason)
        other = await person(body.username)
        if other.id == user.id:
            raise HubError("bad_target", "That's you!")
        await under_limit(user)
        club_id = None
        if body.club:
            club = await clubs.by_slug(body.club)
            mine = await clubs.membership(club.id, user.id) if club else None
            theirs = await clubs.membership(club.id, other.id) if club else None
            if club is None or mine is None or mine.banned or theirs is None:
                raise HubError("no_club", "Club not found", 404)
            club_id = club.id
        values = {
            "reporter_id": user.id,
            "target_id": other.id,
            "target_name": other.username,
            "club_id": club_id,
            "room_code": None,
            "reason": body.reason,
            "note": clean_note(body.note),
            "context": [],
            "priority": events.REASON_PRIORITY.get(body.reason, "normal"),
            "staff": club_id is None,
        }
        await db.add_report(values, actor(user), outbox.names, payload)
        return JSONResponse({"ok": True})

    @api.post("/api/rooms/{code}/report", response_model=schemas.Ok, responses=E)
    async def report_seat(code: str, body: SeatReportBody, request: Request) -> JSONResponse:
        """Report someone in your room. Their recent chat lines go with it, taken by the server."""
        check_same_origin(request, settings)
        user = await me(request)
        reason_ok(body.reason)
        if hub.seated(code, user.id) is None:
            raise HubError("not_in_room", "Join the room first", 403)
        seat = hub.seat_of(code, body.player_id)
        if seat is None:
            raise HubError("bad_target", "That person isn't in this room", 404)
        room, name, account = seat
        if account == user.id:
            raise HubError("bad_target", "That's you!")
        await under_limit(user)
        values = {
            "reporter_id": user.id,
            "target_id": account,
            "target_name": name,
            "club_id": room.club_id,
            "room_code": room.code,
            "reason": body.reason,
            "note": clean_note(body.note),
            "context": hub.said(room, body.player_id),
            "priority": events.REASON_PRIORITY.get(body.reason, "normal"),
            "staff": room.club_id is None,
        }
        await db.add_report(values, actor(user), outbox.names, payload)
        if body.block and account is not None:
            await do_block(user, account)
        return JSONResponse({"ok": True})

    # -- the club moderators' queue -------------------------------------------------------------------------
    async def moderator(slug: str, user: Any) -> tuple[Any, str]:
        club = await clubs.by_slug(slug)
        member = await clubs.membership(club.id, user.id) if club is not None else None
        if club is None or member is None or member.banned:
            raise HubError("no_club", "Club not found", 404)
        if not policy.may_invite(member.role):  # moderator and up
            raise HubError("not_allowed", "Only the club's moderators can see reports", 403)
        return club, member.role

    async def roles(club_id: int) -> dict[int, tuple[str, str]]:
        return {m.user_id: (m.username, m.role) for m in await clubs.members(club_id)}

    @api.get("/api/clubs/{slug}/reports", response_model=schemas.ClubReports, responses=E)
    async def club_reports(slug: str, request: Request) -> JSONResponse:
        user = await me(request)
        club, role = await moderator(slug, user)
        members = await roles(club.id)
        reports = await db.club_reports(club.id)
        timelines = await db.timelines([r.id for r in reports])
        rows = []
        for r in reports:
            target_role = members.get(r.target_id, ("", ""))[1] if r.target_id else ""
            rows.append(
                {
                    "id": r.id,
                    "target": r.target_name,
                    "member": r.target_id in members,
                    "reason": REASONS.get(r.reason, r.reason),
                    "note": r.note,
                    "context": [
                        {"name": c.get("name", ""), "text": c.get("text", "")} for c in r.context or []
                    ],
                    "room": r.room_code,
                    "status": r.status,
                    "at": aware(r.created_at).isoformat(),
                    # Act on people below you; a report about yourself or someone above goes up instead.
                    "can_act": r.status in events.OPEN_STATUSES
                    and r.target_id != user.id
                    and (not target_role or policy.may_remove(role, target_role)),
                    **case_view(r),
                    "history": [history(e) for e in timelines.get(r.id, [])],
                }
            )
        mutes = await db.club_mutes(club.id)
        muted = [
            {"username": members[uid][0], "until": until.isoformat()}
            for uid, until in mutes.items()
            if uid in members
        ]
        actions = [
            {
                "actor": a.actor_name,
                "target": a.target_name,
                "action": a.action,
                "note": a.note,
                "at": aware(a.created_at).isoformat(),
            }
            for a in await db.club_actions(club.id)
        ]
        body = {"reports": rows, "muted": muted, "actions": actions, "reasons": REASONS}
        return JSONResponse(body, headers={"Cache-Control": "no-store"})

    @api.post("/api/clubs/{slug}/reports/{report_id}", response_model=schemas.Ok, responses=E)
    async def act(slug: str, report_id: int, body: ActBody, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await me(request)
        club, role = await moderator(slug, user)
        r = await db.report(report_id)
        if r is None or r.club_id != club.id:
            raise HubError("no_report", "That report isn't here", 404)
        if r.status not in events.OPEN_STATUSES:
            raise HubError("handled", "Someone already handled that report", 409)
        if body.action not in ACTIONS:
            raise HubError("bad_input", "Unknown action")
        members = await roles(club.id)
        target = members.get(r.target_id) if r.target_id is not None else None
        if body.action in ("mute", "remove", "ban"):
            if target is None:
                raise HubError(
                    "not_a_member", "They aren't in the club. Dismiss it, or send it to staff", 409
                )
            if r.target_id == user.id or not policy.may_remove(role, target[1]):
                raise HubError("not_allowed", "You can't act on that person. Send it to staff instead", 403)
        note = ""
        if body.action == "mute":
            if body.hours not in MUTE_HOURS:
                raise HubError("bad_input", "Mute for 1 hour, 1 day or 1 week")
            until = datetime.now(UTC) + timedelta(hours=body.hours)
            await db.mute_member(club.id, r.target_id, until)
            hub.club_mute(club.id, r.target_id, until.timestamp())
            note = f"{body.hours} h"
        elif body.action in ("remove", "ban"):
            await clubs.remove(club.id, r.target_id, body.action == "ban")
            presence.leave_club(club.id, r.target_id)
        status = {"dismiss": "dismissed", "escalate": "escalated"}.get(body.action, "actioned")
        await db.update_report(
            r.id,
            {"status": status, "handled_by": user.id, "handled_at": datetime.now(UTC)}
            | ({"staff": True} if body.action == "escalate" else {}),
            "action",
            actor(user),
            {"action": body.action, "hours": body.hours}
            if body.action == "mute"
            else {"action": body.action},
            outbox.names,
            payload,
        )
        await db.log_action(club.id, user, r.target_name, body.action, note)
        return JSONResponse({"ok": True})

    @api.post("/api/clubs/{slug}/unmute", response_model=schemas.Ok, responses=E)
    async def unmute(slug: str, body: PersonBody, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await me(request)
        club, _ = await moderator(slug, user)
        other = await person(body.username)
        await db.mute_member(club.id, other.id, None)
        hub.club_mute(club.id, other.id, None)
        await db.log_action(club.id, user, other.username, "unmute", "")
        return JSONResponse({"ok": True})

    # -- your data and the privacy notice --------------------------------------------------------------------
    @api.get("/api/me/export", response_model=dict[str, Any], responses=E)
    async def export(request: Request) -> Response:
        """Everything kept about your account, as a file to download."""
        user = await me(request)
        data = {"exported_at": datetime.now(UTC).isoformat(), **await db.export(user.id)}
        return Response(
            json.dumps(data, indent=2, ensure_ascii=False),
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="snazzlebop-my-data.json"',
                "Cache-Control": "no-store",
            },
        )

    @api.get("/api/site", response_model=schemas.SiteInfo)
    async def site() -> JSONResponse:
        """Public facts the pages need: who to contact about privacy."""
        return JSONResponse(
            {"privacy_contact": settings.privacy_contact or None, "operator": settings.operator_name or None}
        )

    return api
