"""Events other systems can rely on: what a report looks like when it leaves Snazzlebop.

Reports are cases. Every change to one (filed, more added, triaged, acted on, a ticket linked) is
written to the report's timeline and, in the same database transaction, queued as an event in the
outbox (outbox.py), which delivers it to each configured destination: a signed webhook today (Jira
Automation, an AI triage service, a support desk...), more later, without touching the report code.

The payload is versioned (`v`). Fields are only ever added within a version; renaming or removing one
means a new version. People are referred to by pseudonymous ids (stable per account, meaningless
outside this system), never by email or internal id; only the reported person's display name is
included, because whoever handles the case needs it.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import UTC
from typing import Any

SCHEMA_VERSION = 1
REPORT_CREATED = "report.created"
REPORT_UPDATED = "report.updated"

STATUSES = ("open", "triaged", "escalated", "dismissed", "actioned")
OPEN_STATUSES = ("open", "triaged")  # still waiting for a person to decide
PRIORITIES = ("low", "normal", "high", "urgent")
REASONS = {
    "harassment": "Harassment or bullying",
    "hate": "Hate or slurs",
    "cheating": "Cheating or griefing",
    "spam": "Spam",
    "sexual": "Sexual content",
    "other": "Something else",
}
# A reason's starting priority; triage (a person or a model) can change it.
REASON_PRIORITY = {"hate": "high", "sexual": "high", "harassment": "normal"}
SYSTEM_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,19}$")


def pseudonym(secret: str, kind: str, raw_id: int | None) -> str | None:
    """A stable, opaque id for an account ("usr_3f9a..."): the same person always gets the same one,
    and it can't be turned back into the account."""
    if raw_id is None:
        return None
    digest = hmac.new(secret.encode(), f"{kind}:{raw_id}".encode(), hashlib.sha256).hexdigest()
    return f"usr_{digest[:16]}"


def report_payload(report: Any, club: Any, site: str, secret: str) -> dict[str, Any]:
    """Version 1 of a report as other systems see it."""
    return {
        "v": SCHEMA_VERSION,
        "id": report.public_id,
        "status": report.status,
        "queue": "staff" if report.staff else "club",  # who decides: platform staff or the club's moderators
        "priority": report.priority,
        "reason": report.reason,
        "reason_label": REASONS.get(report.reason, report.reason),
        "note": report.note,
        "context": list(report.context or []),  # their recent chat lines, captured by the server
        "reported": {"name": report.target_name, "ref": pseudonym(secret, "user", report.target_id)},
        "reporter": {"ref": pseudonym(secret, "user", report.reporter_id)},
        "club": {"slug": club.slug, "name": club.name} if club is not None else None,
        "room": report.room_code,
        "assignee": report.assignee,
        "triage": dict(report.triage or {}) or None,
        "external": dict(report.external or {}),
        "created_at": _iso(report.created_at),
        "updated_at": _iso(report.updated_at or report.created_at),
        "links": {"moderate": f"{site}/clubs/{club.slug}/reports" if club is not None else None},
    }


def _iso(when: Any) -> str:
    return (when if when.tzinfo else when.replace(tzinfo=UTC)).isoformat()


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """The webhook signature: HMAC-SHA256 over "<timestamp>.<body>", sent as "sha256=<hex>". Receivers
    recompute it and refuse anything older than a few minutes (replays)."""
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"sha256={mac}"
