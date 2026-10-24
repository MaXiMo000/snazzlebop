"""Places: proving you belong to a college or company, with a code sent to your address there.

- A place has email domains ("iitd.ac.in"); an address on one of them, or a subdomain of one
  ("cs.iitd.ac.in"), proves membership. Free email providers never map to a place.
- Verifying: we send a 6-digit code to that address (valid 15 minutes, 5 tries, one a minute per
  account). The address itself is never stored: only a keyed hash, so one address verifies one
  account per place.
- A verification lasts a year; after that the badge shows as alumni until it's verified again.
- An address whose domain no place has yet is noted as a request for staff (staff.py adds places).
- Clubs can require a verified place to join (clubs/routes.py).
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import emails, schemas
from .accounts import EMAIL_MAX, check_same_origin, clean_email, session_user
from .config import Settings
from .db import aware
from .mailer import Mailer
from .rooms import HubError

E = schemas.ERRORS
CODE_SECONDS = 15 * 60
CODE_TRIES = 5
CODE_GAP = 60.0
VALID_DAYS = 365
KINDS = ("college", "company")
FREE_PROVIDERS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "yahoo.com",
        "ymail.com",
        "rocketmail.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
        "pm.me",
        "gmx.com",
        "gmx.net",
        "mail.com",
        "yandex.com",
        "zoho.com",
        "rediffmail.com",
        "tutanota.com",
        "fastmail.com",
        "hey.com",
        "qq.com",
        "163.com",
    }
)
# Country editions (yahoo.co.in, hotmail.co.uk, outlook.fr...): the brand is enough to know.
FREE_BRANDS = ("gmail", "yahoo", "hotmail", "outlook", "live", "rediffmail", "yandex", "gmx")
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
DOMAIN_RE = re.compile(rf"^{_LABEL}(?:\.{_LABEL})+$")


# -- pure helpers --------------------------------------------------------------------------------------
def domain_of(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower()


def is_free(domain: str) -> bool:
    if domain in FREE_PROVIDERS:
        return True
    first = domain.split(".", 1)[0]
    return first in FREE_BRANDS


def clean_domain(raw: Any) -> str:
    domain = str(raw or "").strip().lower().removeprefix("@")
    if len(domain) > 120 or not DOMAIN_RE.fullmatch(domain):
        raise ValueError(f"{raw!r} isn't a domain like iitd.ac.in")
    if is_free(domain):
        raise ValueError(f"{domain} is a free email provider: it can't prove anyone belongs anywhere")
    return domain


def slug_for(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40].strip("-")
    return base or f"place-{secrets.token_hex(3)}"


def email_hash(secret: str, email: str) -> str:
    return hmac.new(secret.encode(), b"place-email:" + email.encode(), hashlib.sha256).hexdigest()


def code_hash(secret: str, user_id: int, code: str) -> str:
    return hmac.new(secret.encode(), f"place-code:{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def standing(expires_at: datetime, now: datetime | None = None) -> str:
    return "verified" if expires_at > (now or datetime.now(UTC)) else "alumni"


# -- routes --------------------------------------------------------------------------------------------
class StartBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    email: str = Field(max_length=EMAIL_MAX)


class CodeBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    code: str = Field(max_length=12)


def router(settings: Settings, db: Any, mail: Mailer) -> APIRouter:
    api = APIRouter()
    sent: dict[int, float] = {}  # account -> when its last code went out

    async def me(request: Request) -> Any:
        if not db.ready:
            raise HubError("accounts_down", "Accounts are unavailable right now. Games still work!", 503)
        user = await session_user(request, db)
        if user is None:
            raise HubError("signed_out", "Sign in first", 401)
        return user

    async def mine(user: Any) -> list[dict[str, Any]]:
        rows = (await db.user_places([user.id])).get(user.id, [])
        return [
            {
                "slug": place.slug,
                "name": place.name,
                "kind": place.kind,
                "status": standing(until),
                "verified_at": at.isoformat(),
                "expires_at": until.isoformat(),
            }
            for place, at, until in rows
        ]

    @api.get("/api/places", response_model=schemas.PlaceList, responses=E)
    async def all_places(request: Request) -> JSONResponse:
        """The places people can verify (for a club to pick the one it's for)."""
        await me(request)
        rows = [{"slug": p.slug, "name": p.name, "kind": p.kind} for p, _, _ in await db.places()]
        return JSONResponse({"places": rows}, headers={"Cache-Control": "no-store"})

    @api.get("/api/me/places", response_model=schemas.MyPlaces, responses=E)
    async def my_places(request: Request) -> JSONResponse:
        user = await me(request)
        body = {"places": await mine(user), "mail": mail.enabled}
        return JSONResponse(body, headers={"Cache-Control": "no-store"})

    @api.post("/api/me/places/start", response_model=schemas.PlaceStarted, responses=E)
    async def start(body: StartBody, request: Request) -> JSONResponse:
        """Send a code to a college or work address."""
        check_same_origin(request, settings)
        user = await me(request)
        if not mail.enabled:
            raise HubError("mail_off", "Email isn't set up on this site yet", 503)
        email = clean_email(body.email)
        domain = domain_of(email)
        if is_free(domain):
            raise HubError("free_email", "Use your college or work address, not a personal one")
        place = await db.place_for_domain(domain)
        if place is None:
            await db.note_place_request(domain)
            raise HubError(
                "unknown_place",
                f"We don't know {domain} yet. We've noted it, and you'll be able to verify once it's added",
                404,
            )
        hashed = email_hash(settings.secret_key, email)
        owner = await db.place_email_owner(place.id, hashed)
        if owner is not None and owner != user.id:
            raise HubError("email_used", "That address already verified another account", 409)
        now = time.monotonic()
        if now - sent.get(user.id, -1e9) < CODE_GAP:
            raise HubError("slow_down", "We just sent a code. Wait a minute before asking for another", 429)
        if len(sent) > 20000:
            sent.clear()
        sent[user.id] = now
        code = f"{secrets.randbelow(1_000_000):06d}"
        await db.start_place_code(
            user.id, place.id, hashed, code_hash(settings.secret_key, user.id, code), CODE_SECONDS
        )
        mail.send(email, emails.place_code(settings.site, user.username, place.name, code), "place-code")
        return JSONResponse(
            {"place": {"slug": place.slug, "name": place.name}, "sent_to": emails.mask(email)}
        )

    @api.post("/api/me/places/confirm", response_model=schemas.MyPlaces, responses=E)
    async def confirm(body: CodeBody, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await me(request)
        pending = await db.place_code(user.id)
        if pending is None or aware(pending.expires_at) < datetime.now(UTC):
            raise HubError("no_code", "That code has expired. Ask for a new one", 400)
        if pending.attempts >= CODE_TRIES:
            raise HubError("too_many_tries", "Too many wrong codes. Ask for a new one", 429)
        given = re.sub(r"\D", "", body.code)
        if not hmac.compare_digest(code_hash(settings.secret_key, user.id, given), pending.code_hash):
            await db.place_code_failed(user.id)
            raise HubError("bad_code", "That code isn't right. Check the email and try again", 400)
        if not await db.verify_place(user.id, pending.place_id, pending.email_hash, VALID_DAYS):
            raise HubError("email_used", "That address already verified another account", 409)
        return JSONResponse({"places": await mine(user), "mail": mail.enabled})

    @api.post("/api/me/places/{slug}/remove", response_model=schemas.MyPlaces, responses=E)
    async def remove(slug: str, request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await me(request)
        place = await db.place_by_slug(slug) if len(slug) <= 48 else None
        if place is not None:
            await db.remove_user_place(user.id, place.id)
        return JSONResponse({"places": await mine(user), "mail": mail.enabled})

    return api
