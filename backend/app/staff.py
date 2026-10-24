"""The platform staff console: the cases no club can decide, and account suspensions.

- Who: the accounts named in STAFF_USERNAMES (a dashboard secret, never the repo), and only while their
  authenticator app is on. Everyone else gets "not found", so the console doesn't announce itself.
- What staff see: cases escalated by a club's moderators or an integration, and reports that aren't
  about a club at all, with the same case view moderators get (events.py).
- What staff do: dismiss; suspend the reported account for 1, 7 or 30 days or for good (it is signed
  out everywhere and can't sign in until then); hand an escalated case back to its club; lift a
  suspension. Every action goes on the case's timeline, out through the outbox, and into the audit log.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import events, schemas
from .accounts import USERNAME_RE, check_same_origin, session_user
from .config import Settings
from .db import aware
from .outbox import Outbox
from .places import KINDS, clean_domain, slug_for
from .rooms import HubError
from .safety import case_view, history

E = schemas.ERRORS
SUSPEND_DAYS = (1, 7, 30, 0)  # 0: for good
FOREVER = datetime(9999, 1, 1, tzinfo=UTC)


class StaffActBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: str = Field(max_length=12)  # dismiss | suspend | return
    days: int | None = None  # for suspend: 1, 7, 30, or 0 for good
    reason: str = Field(default="", max_length=200)


class PlaceBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    slug: str | None = Field(default=None, max_length=48)  # an existing place to change; none: a new one
    name: str = Field(min_length=2, max_length=80)
    kind: str = Field(max_length=10)
    domains: list[str] = Field(min_length=1, max_length=20)


class DomainBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    domain: str = Field(max_length=120)


class UsernameBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    username: str = Field(max_length=64)


def router(settings: Settings, db: Any, outbox: Outbox) -> APIRouter:
    api = APIRouter()

    def payload(report: Any, club: Any) -> dict[str, Any]:
        return events.report_payload(report, club, settings.site, settings.secret_key)

    async def staff_user(request: Request) -> Any:
        if not db.ready:
            raise HubError("accounts_down", "Accounts are unavailable right now", 503)
        user = await session_user(request, db)
        if user is None or user.username_key not in settings.staff_usernames:
            raise HubError("not_found", "Not found", 404)
        mfa = await db.mfa(user.id)
        if mfa is None or mfa.enabled_at is None:
            raise HubError("needs_mfa", "Turn on your authenticator app to use the staff console", 403)
        return user

    def is_staff_account(user: Any) -> bool:
        return user.username_key in settings.staff_usernames

    @api.get("/api/staff/reports", response_model=schemas.StaffQueue, responses=E)
    async def queue(request: Request) -> JSONResponse:
        await staff_user(request)
        reports = await db.staff_reports()
        timelines = await db.timelines([r.id for r in reports])
        names = await db.club_names({r.club_id for r in reports if r.club_id is not None})
        targets = await db.users_by_id([r.target_id for r in reports if r.target_id is not None])
        rows = []
        for r in reports:
            target = targets.get(r.target_id) if r.target_id is not None else None
            rows.append(
                {
                    "id": r.id,
                    "target": r.target_name,
                    "account": target.username if target is not None else None,
                    "reason": events.REASONS.get(r.reason, r.reason),
                    "note": r.note,
                    "context": [
                        {"name": c.get("name", ""), "text": c.get("text", "")} for c in r.context or []
                    ],
                    "room": r.room_code,
                    "club": names.get(r.club_id) if r.club_id is not None else None,
                    "status": r.status,
                    "at": aware(r.created_at).isoformat(),
                    "can_suspend": r.status in ("open", "triaged", "escalated")
                    and target is not None
                    and not is_staff_account(target),
                    "can_return": r.status == "escalated" and r.club_id is not None,
                    **case_view(r),
                    "history": [history(e) for e in timelines.get(r.id, [])],
                }
            )
        suspended = [
            {
                "username": u.username,
                "until": None
                if aware(u.suspended_until) >= FOREVER
                else aware(u.suspended_until).isoformat(),
                "reason": u.suspend_reason,
            }
            for u in await db.suspended_users()
        ]
        actions = [
            {
                "actor": a.actor_name,
                "target": a.target_name,
                "action": a.action,
                "note": a.note,
                "at": aware(a.created_at).isoformat(),
            }
            for a in await db.staff_actions()
        ]
        return JSONResponse(
            {"reports": rows, "suspended": suspended, "actions": actions},
            headers={"Cache-Control": "no-store"},
        )

    @api.post("/api/staff/reports/{report_id}", response_model=schemas.Ok, responses=E)
    async def act(report_id: int, body: StaffActBody, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await staff_user(request)
        r = await db.report(report_id)
        if r is None or not r.staff:
            raise HubError("no_report", "That case isn't in the staff queue", 404)
        if r.status not in ("open", "triaged", "escalated"):
            raise HubError("handled", "Someone already handled that case", 409)
        reason = " ".join(body.reason.split())[:200]
        changes: dict[str, Any] = {"handled_by": user.id, "handled_at": datetime.now(UTC)}
        data: dict[str, Any] = {"action": body.action}
        note = ""
        if body.action == "dismiss":
            changes["status"] = "dismissed"
        elif body.action == "suspend":
            if body.days not in SUSPEND_DAYS:
                raise HubError("bad_input", "Suspend for 1, 7 or 30 days, or for good")
            target = (
                (await db.users_by_id([r.target_id])).get(r.target_id) if r.target_id is not None else None
            )
            if target is None:
                raise HubError(
                    "no_account", "There's no account to suspend (a guest, or it was deleted)", 409
                )
            if target.id == user.id or is_staff_account(target):
                raise HubError("not_allowed", "Staff accounts can't be suspended here", 403)
            until = FOREVER if body.days == 0 else datetime.now(UTC) + timedelta(days=body.days)
            await db.suspend(target.id, until, reason or events.REASONS.get(r.reason, r.reason))
            changes["status"] = "actioned"
            data["days"] = body.days
            note = "for good" if body.days == 0 else f"{body.days} d"
        elif body.action == "return":
            if r.status != "escalated" or r.club_id is None:
                raise HubError("bad_input", "Only an escalated club case can go back to its club")
            changes = {"status": "open", "staff": False}
        else:
            raise HubError("bad_input", "Unknown action")
        if reason:
            data["note"] = reason
        await db.update_report(r.id, changes, "action", f"staff:{user.username}", data, outbox.names, payload)
        await db.log_action(None, user, r.target_name, body.action, note)
        return JSONResponse({"ok": True})

    @api.post("/api/staff/unsuspend", response_model=schemas.Ok, responses=E)
    async def unsuspend(body: UsernameBody, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await staff_user(request)
        name = body.username.strip()
        target = await db.user_by_name(name) if USERNAME_RE.fullmatch(name) else None
        if target is None:
            raise HubError("no_such_user", "No account with that username", 404)
        await db.suspend(target.id, None, "")
        await db.log_action(None, user, target.username, "unsuspend", "")
        return JSONResponse({"ok": True})

    # -- places: the colleges and companies people can verify ------------------------------------------
    async def places_view() -> dict[str, Any]:
        return {
            "places": [
                {"slug": p.slug, "name": p.name, "kind": p.kind, "domains": domains, "members": members}
                for p, domains, members in await db.places()
            ],
            "requests": [
                {"domain": r.domain, "count": r.count, "last_at": aware(r.last_at).isoformat()}
                for r in await db.place_requests()
            ],
        }

    @api.get("/api/staff/places", response_model=schemas.StaffPlaces, responses=E)
    async def list_places(request: Request) -> JSONResponse:
        await staff_user(request)
        return JSONResponse(await places_view(), headers={"Cache-Control": "no-store"})

    @api.post("/api/staff/places", response_model=schemas.StaffPlaces, responses=E)
    async def save_place(body: PlaceBody, request: Request) -> JSONResponse:
        """Add a place, or change one (its name, kind and the full list of its domains)."""
        check_same_origin(request, settings)
        user = await staff_user(request)
        if body.kind not in KINDS:
            raise HubError("bad_input", "A place is a college or a company")
        name = " ".join(body.name.split())
        try:
            domains = sorted({clean_domain(d) for d in body.domains})
        except ValueError as exc:
            raise HubError("bad_input", str(exc)) from None
        if body.slug is not None and await db.place_by_slug(body.slug) is None:
            raise HubError("no_place", "That place doesn't exist", 404)
        slug = body.slug or slug_for(name)
        if body.slug is None and await db.place_by_slug(slug) is not None:
            raise HubError("place_exists", "A place with that name already exists: change it instead", 409)
        taken = await db.save_place(slug, name, body.kind, domains)
        if taken is not None:
            raise HubError("domain_taken", f"{taken} already belongs to another place", 409)
        await db.log_action(None, user, name, "place", ", ".join(domains))
        return JSONResponse(await places_view())

    @api.post("/api/staff/places/requests/decline", response_model=schemas.StaffPlaces, responses=E)
    async def decline(body: DomainBody, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        await staff_user(request)
        await db.decline_place_request(body.domain.strip().lower())
        return JSONResponse(await places_view())

    return api
