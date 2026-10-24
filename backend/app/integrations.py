"""The integration API: how other systems (an AI triage service, Jira, a support desk) read report cases
and write back to them.

- Off unless INTEGRATION_TOKEN is set; then every call needs `Authorization: Bearer <token>`. Server to
  server: no cookies, no browser origin. Wrong or missing token: 401, compared in constant time.
- Reading: the open cases (or any statuses), or one case with its timeline, in the same versioned shape
  the webhook sends (events.report_payload).
- Writing: workflow fields only: status (open, triaged, escalated, dismissed), priority, assignee,
  links to tickets elsewhere ({"jira": {"key": "SNZ-12", "url": "https://..."}}) and triage notes
  ({"label", "score", "summary"}). Acting on a person (mute, remove, ban) stays with human moderators.
  Each write lands on the case's timeline as "integration:<source>" and goes out as a report.updated
  event that names the source, so a system can skip its own echoes.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import events, schemas
from .config import Settings
from .db import aware
from .outbox import Outbox
from .rooms import HubError

E = schemas.ERRORS
SETTABLE_STATUSES = ("open", "triaged", "escalated", "dismissed")


class Ticket(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    key: str = Field(min_length=1, max_length=40)
    url: str | None = Field(default=None, max_length=300)


class Triage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    label: str = Field(min_length=1, max_length=40)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    summary: str = Field(default="", max_length=500)


class UpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: str = Field(min_length=1, max_length=20)  # who is writing: "jira", "ai-triage", ...
    status: str | None = Field(default=None, max_length=12)
    priority: str | None = Field(default=None, max_length=8)
    assignee: str | None = Field(default=None, max_length=80)
    external: dict[str, Ticket] | None = Field(default=None, max_length=5)
    triage: Triage | None = None
    note: str = Field(default="", max_length=300)


def router(settings: Settings, db: Any, outbox: Outbox) -> APIRouter:
    api = APIRouter()

    def payload(report: Any, club: Any) -> dict[str, Any]:
        return events.report_payload(report, club, settings.site, settings.secret_key)

    def authorize(request: Request) -> None:
        if not settings.integration_token:
            raise HubError("not_found", "Not found", 404)
        given = request.headers.get("authorization", "")
        expected = f"Bearer {settings.integration_token}"
        if not hmac.compare_digest(given.encode(), expected.encode()):
            raise HubError("unauthorized", "A valid integration token is required", 401)
        if not db.ready:
            raise HubError("accounts_down", "The database is unavailable", 503)

    async def timeline(report_id: int) -> list[dict[str, Any]]:
        return [
            {"kind": e.kind, "actor": e.actor, "data": e.data or {}, "at": aware(e.created_at).isoformat()}
            for e in (await db.timelines([report_id])).get(report_id, [])
        ]

    async def case(public_id: str) -> tuple[Any, Any]:
        found = await db.report_by_public_id(public_id) if len(public_id) <= 24 else None
        if found is None:
            raise HubError("no_report", "No report with that id", 404)
        return found

    @api.get("/api/integrations/reports", response_model=schemas.IntegrationReports, responses=E)
    async def list_reports(request: Request, status: str = "open,triaged", limit: int = 50) -> JSONResponse:
        """Cases by status (comma separated), newest first. Default: the ones waiting for a decision."""
        authorize(request)
        wanted = tuple(s for s in status.split(",") if s in events.STATUSES)
        if not wanted:
            raise HubError("bad_input", f"status is any of {', '.join(events.STATUSES)}")
        rows = await db.reports_for_integration(wanted, max(1, min(limit, 200)))
        return JSONResponse(
            {"reports": [payload(r, c) for r, c in rows]}, headers={"Cache-Control": "no-store"}
        )

    @api.get("/api/integrations/reports/{public_id}", response_model=schemas.IntegrationReport, responses=E)
    async def get_report(public_id: str, request: Request) -> JSONResponse:
        authorize(request)
        report, club = await case(public_id)
        body = {"report": payload(report, club), "timeline": await timeline(report.id)}
        return JSONResponse(body, headers={"Cache-Control": "no-store"})

    @api.post("/api/integrations/reports/{public_id}", response_model=schemas.IntegrationReport, responses=E)
    async def update_report(public_id: str, body: UpdateBody, request: Request) -> JSONResponse:
        authorize(request)
        report, _ = await case(public_id)
        if not events.SYSTEM_RE.fullmatch(body.source):
            raise HubError("bad_input", "source is a short name like jira or ai-triage")
        changes: dict[str, Any] = {}
        if body.status is not None:
            if body.status not in SETTABLE_STATUSES:
                raise HubError("bad_input", f"status is any of {', '.join(SETTABLE_STATUSES)}")
            if report.status in ("actioned",):
                raise HubError("handled", "A moderator already acted on this case", 409)
            changes["status"] = body.status
        if body.priority is not None:
            if body.priority not in events.PRIORITIES:
                raise HubError("bad_input", f"priority is any of {', '.join(events.PRIORITIES)}")
            changes["priority"] = body.priority
        if body.assignee is not None:
            changes["assignee"] = body.assignee.strip() or None
        if body.external:
            for system, ticket in body.external.items():
                if not events.SYSTEM_RE.fullmatch(system):
                    raise HubError("bad_input", "Ticket systems are short names like jira")
                if ticket.url is not None and not ticket.url.startswith("https://"):
                    raise HubError("bad_input", "Ticket links must be https")
            changes["external"] = {k: v.model_dump() for k, v in body.external.items()}
        if body.triage is not None:
            changes["triage"] = {**body.triage.model_dump(), "by": body.source}
        if not changes and not body.note:
            raise HubError("bad_input", "Nothing to change")
        kind = (
            "triage"
            if set(changes) == {"triage"}
            else "external"
            if set(changes) == {"external"}
            else "status"
            if set(changes) == {"status"}
            else "update"
        )
        data: dict[str, Any] = {**changes, "note": body.note, "source": body.source}
        if body.triage is not None:
            data.update(label=body.triage.label, score=body.triage.score)
        updated = await db.update_report(
            report.id, changes, kind, f"integration:{body.source}", data, outbox.names, payload
        )
        if updated is None:
            raise HubError("no_report", "No report with that id", 404)
        _, club = await case(public_id)
        return JSONResponse({"report": payload(updated, club), "timeline": await timeline(updated.id)})

    @api.get("/api/integrations/health", response_model=schemas.IntegrationHealth, responses=E)
    async def health(request: Request) -> JSONResponse:
        """For monitoring: events waiting to go out, and ones that gave up after every retry."""
        authorize(request)
        return JSONResponse({**await db.outbox_stats(), "sinks": outbox.names})

    return api
