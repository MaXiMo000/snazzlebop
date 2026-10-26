"""Accounts, coins and power-ups.

Sign-up is a username and a password. Everyone gets a one-time recovery code (shown once, stored only
as a keyed hash) that resets a forgotten password. An email address is optional: once confirmed, it
also signs in, gets reset links, and is told about changes to the account (emails.py, mailer.py).

Security:
- Passwords: scrypt (stdlib), per-user salt, run off the event loop. Max 128 chars (scrypt is
  costly on purpose: a megabyte "password" must not become a CPU attack).
- Sessions: a random 256-bit token in an HttpOnly, SameSite=Strict cookie (Secure in production).
  Only its SHA-256 is stored, so a database leak doesn't leak sessions. Logout deletes it; a
  password change or recovery deletes every session of that account.
- Cross-site requests: SameSite=Strict, JSON-only bodies, and a strict Origin check on every
  state-changing call.
- Guessing: per-IP rate limits on every /api/auth route, plus a per-username lockout that doubles
  after repeated failures. A wrong username and a wrong password get the same message and take the
  same time (a dummy hash runs for unknown names).

Coins: finishing places in any game with 2+ players earn coins (1st 50, 2nd 30, 3rd 20, 4th 10,
everyone else 5; ties share the better place), up to DAILY_COIN_CAP a day. Coins buy power-ups (the
show's power cards), and a signed-in player can use one per game.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import re
import secrets
import time
import unicodedata
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import HTTPConnection

from . import emails, mfa, oidc, schemas
from . import party as partylib
from .coins import DAILY_COIN_CAP, EMOTE_PRICES, GAME_POWER_PRICES, PARTY_PRICES, season_of
from .config import Settings
from .db import aware, suspended
from .games import REGISTRY
from .mailer import Mailer
from .rooms import HubError
from .security import RateLimiter, client_ip

log = logging.getLogger("snazzlebop.accounts")
SESSION_COOKIE = "sb_session"
SESSION_DAYS = 30
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,20}$")
PASSWORD_MIN, PASSWORD_MAX = 8, 128
COMMON_PASSWORDS = frozenset(
    [
        "password",
        "password1",
        "password123",
        "12345678",
        "123456789",
        "1234567890",
        "qwerty123",
        "qwertyuiop",
        "iloveyou",
        "11111111",
        "00000000",
        "abc12345",
        "letmein1",
        "welcome1",
        "sunshine",
        "monkey12",
        "football",
        "snazzlebop",
    ]
)
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1  # ~16 MB and tens of milliseconds per hash
LOCK_AFTER = 5  # failed logins for one username before it's locked for a while
LOCK_SECONDS = 60.0
DEVICE_COOKIE = "sb_device"
EMAIL_MAX = 254
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
EMAIL_RE = re.compile(rf"^[^@\s]{{1,64}}@{_LABEL}(?:\.{_LABEL})+$")
VERIFY_SECONDS = 2 * 86400
RESET_SECONDS = 30 * 60
LINK_SECONDS = 15 * 60  # an emailed sign-in link
GOOGLE_CODE_SECONDS = 5 * 60  # after Google, to enter the authenticator code
FRESH_SECONDS = 15 * 60  # how recent a sign-in stands in for a password (accounts without one)
RESET_GAP = 60.0  # one reset email per account per minute, whatever the rate limits allow


# -- validation --------------------------------------------------------------------------------------
def clean_username(raw: object) -> str:
    if not isinstance(raw, str):
        raise HubError("bad_username", "Usernames are 3-20 letters, numbers, dots, dashes or underscores")
    name = unicodedata.normalize("NFKC", raw).strip()
    if not USERNAME_RE.fullmatch(name):
        raise HubError("bad_username", "Usernames are 3-20 letters, numbers, dots, dashes or underscores")
    return name


def clean_email(raw: object) -> str:
    if not isinstance(raw, str):
        raise HubError("bad_email", "That doesn't look like an email address")
    email = raw.strip().lower()
    if len(email) > EMAIL_MAX or not email.isprintable() or not EMAIL_RE.fullmatch(email):
        raise HubError("bad_email", "That doesn't look like an email address")
    return email


def check_password(raw: object, username: str = "") -> str:
    if not isinstance(raw, str) or not PASSWORD_MIN <= len(raw) <= PASSWORD_MAX:
        raise HubError("weak_password", f"Passwords need {PASSWORD_MIN} to {PASSWORD_MAX} characters")
    if raw.casefold() in COMMON_PASSWORDS or (username and raw.casefold() == username.casefold()):
        raise HubError("weak_password", "That password is too easy to guess")
    return raw


# -- hashing -----------------------------------------------------------------------------------------
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, maxmem=64 * 2**20, dklen=32
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt, want = stored.split("$")
        if kind != "scrypt":
            return False
        got = hashlib.scrypt(
            password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), maxmem=64 * 2**20, dklen=32
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, _unb64(want))


DUMMY_HASH = hash_password(secrets.token_urlsafe(16))  # compared against when a username doesn't exist


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_recovery_code() -> str:
    """Four groups of five letters/digits (no lookalikes): about 100 bits."""
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(20))
    return "-".join(raw[i : i + 5] for i in range(0, 20, 5))


def recovery_hash(secret: str, code: str) -> str:
    norm = re.sub(r"[^A-Z0-9]", "", code.upper())
    return hmac.new(secret.encode(), b"recovery:" + norm.encode(), hashlib.sha256).hexdigest()


# -- brute-force brake: per-username lockout -----------------------------------------------------------
class Lockout:
    def __init__(self, clock: Any = time.monotonic, max_keys: int = 20000) -> None:
        self.clock = clock
        self.max_keys = max_keys
        self.fails: dict[str, tuple[int, float]] = {}  # username -> (failures, locked until)

    def locked(self, key: str) -> bool:
        n, until = self.fails.get(key, (0, 0.0))
        return n >= LOCK_AFTER and self.clock() < until

    def fail(self, key: str) -> None:
        if len(self.fails) >= self.max_keys:
            self.fails.clear()  # memory bound; the per-IP limits still apply
        n, _ = self.fails.get(key, (0, 0.0))
        n += 1
        wait = LOCK_SECONDS * 2 ** max(0, n - LOCK_AFTER) if n >= LOCK_AFTER else 0.0
        self.fails[key] = (n, self.clock() + min(wait, 3600.0))

    def ok(self, key: str) -> None:
        self.fails.pop(key, None)


# -- HTTP --------------------------------------------------------------------------------------------
class SignupBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(max_length=64)
    password: str = Field(max_length=PASSWORD_MAX)
    email: str | None = Field(default=None, max_length=EMAIL_MAX)


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(max_length=EMAIL_MAX)  # the username, or an email confirmed on the account
    password: str = Field(max_length=PASSWORD_MAX)
    code: str | None = Field(default=None, max_length=32)  # authenticator or backup code, when it is on


class ForgotBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    login: str = Field(max_length=EMAIL_MAX)  # username or email


class ResetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(max_length=100)
    new_password: str = Field(max_length=PASSWORD_MAX)
    code: str | None = Field(default=None, max_length=32)


class EmailOnlyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=EMAIL_MAX)


class LinkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(max_length=100)
    code: str | None = Field(default=None, max_length=32)  # authenticator or backup code, when it is on


class PasswordOnlyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(default="", max_length=PASSWORD_MAX)


class TokenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(max_length=100)


class EmailBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=EMAIL_MAX)
    password: str = Field(max_length=PASSWORD_MAX)


class RecoverBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(max_length=64)
    recovery_code: str = Field(max_length=64)
    new_password: str = Field(max_length=PASSWORD_MAX)
    code: str | None = Field(default=None, max_length=32)  # authenticator or backup code, when it is on


class PasswordBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(max_length=PASSWORD_MAX)
    new_password: str = Field(max_length=PASSWORD_MAX)


class ConfirmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(max_length=PASSWORD_MAX)
    code: str | None = Field(default=None, max_length=32)  # authenticator or backup code, when it is on


class CodeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(max_length=32)


class MfaOffBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(max_length=PASSWORD_MAX)
    code: str = Field(max_length=32)


class FriendBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(max_length=64)


class BuyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str = Field(max_length=32)


def public_user(user: Any) -> dict[str, Any]:
    """The signed-in account as its owner sees it (never shown to anyone else)."""
    return {
        "username": user.username,
        "coins": user.coins,
        "powerups": dict(user.powerups or {}),
        "email": user.email,
        "email_verified": bool(user.email_verified),
        "has_password": bool(user.pw_hash),
    }


async def session_user(request: HTTPConnection, db: Any) -> Any:
    """The signed-in account behind this request's (or WebSocket's) cookie, or None."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token or len(token) > 100 or not db.ready:
        return None
    return await db.user_for_session(token_hash(token))


def check_same_origin(request: Request, settings: Settings) -> None:
    """No cross-site writes: the browser's Origin must be ours (SameSite=Strict backs this up)."""
    origin = request.headers.get("origin")
    if origin is None:
        if settings.is_production:
            raise HubError("bad_origin", "That request came from the wrong place", 403)
        return
    if origin not in settings.allowed_origins:
        raise HubError("bad_origin", "That request came from the wrong place", 403)


def router(
    settings: Settings,
    db: Any,
    limiter: RateLimiter,
    hosting: Callable[[set[int]], dict[int, str]] = lambda ids: {},
    mailer: Mailer | None = None,
    status_of: Callable[[set[int]], Awaitable[dict[int, tuple[str, str | None]]]] | None = None,
    forget: Callable[[int, list[int]], None] = lambda user_id, closed: None,
    google: oidc.Google | None = None,
) -> APIRouter:
    api = APIRouter()
    lockout = Lockout()
    mail = mailer or Mailer(settings)
    site = settings.site
    reset_sent: dict[int, float] = {}  # account -> when its last reset email went out
    google = google or oidc.Google("", "", "")
    box = oidc.StateBox(settings.secret_key)
    link_sent: dict[int, float] = {}  # account -> when its last sign-in link went out

    def ip(request: Request) -> str:
        return client_ip(request.scope, settings.trusted_proxy_hops, settings.client_ip_header)

    def same_origin(request: Request) -> None:
        check_same_origin(request, settings)

    def need_db() -> None:
        if not db.ready:
            raise HubError("accounts_down", "Accounts are unavailable right now. Games still work!", 503)

    def set_session(resp: Response, token: str) -> None:
        resp.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=SESSION_DAYS * 86400,
            httponly=True,
            secure=settings.is_production,
            samesite="strict",
            path="/",
        )

    async def start_session(user_id: int, request: Request) -> str:
        token = secrets.token_urlsafe(32)
        device = emails.describe_device(request.headers.get("user-agent", "")[:400])
        await db.create_session(token_hash(token), user_id, SESSION_DAYS * 86400, device)
        return token

    async def current(request: Request) -> Any:
        return await session_user(request, db)

    # -- email ---------------------------------------------------------------------------------------
    def tell(user: Any, email: emails.Email, kind: str) -> None:
        """Send to the account's confirmed address, if it has one."""
        if user.email and user.email_verified:
            mail.send(user.email, email, kind)

    def notice(user: Any, subject: str, what: str) -> None:
        tell(user, emails.notice(site, user.username, subject, what), "notice")

    async def send_verify(user: Any, email: str, changed: bool) -> None:
        if not mail.enabled:
            return
        token = secrets.token_urlsafe(32)
        await db.add_token(token_hash(token), user.id, "verify", email, VERIFY_SECONDS)
        url = f"{site}/account/verify#{token}"  # the fragment never reaches a server log
        mail.send(email, emails.verify_email(site, user.username, url, changed), "verify")

    async def signed_in(resp: Response, request: Request, user: Any) -> None:
        """A sign-in worked: remember this browser, and warn the owner about one we haven't seen."""
        raw = request.cookies.get(DEVICE_COOKIE, "")
        device = raw if re.fullmatch(r"[A-Za-z0-9_-]{43}", raw) else secrets.token_urlsafe(32)
        seen, had_any = await db.note_device(user.id, token_hash(device))
        if not seen and had_any:
            ua = request.headers.get("user-agent", "")[:400]
            tell(user, emails.new_device(site, user.username, emails.describe_device(ua)), "new-device")
        resp.set_cookie(
            DEVICE_COOKIE,
            device,
            max_age=400 * 86400,
            httponly=True,
            secure=settings.is_production,
            samesite="strict",
            path="/",
        )

    async def confirm(
        user: Any, password: str, request: Request, wrong: str = "That password isn't right"
    ) -> None:
        """Prove it's really you before a sensitive change: your password, or, for an account that
        signs in only with Google, a sign-in within the last few minutes."""
        if user.pw_hash:
            if not await asyncio.to_thread(verify_password, password, user.pw_hash):
                raise HubError("bad_login", wrong, 401)
            return
        started = await db.session_started(token_hash(request.cookies.get(SESSION_COOKIE, "")))
        if started is None or time.time() - started.timestamp() > FRESH_SECONDS:
            raise HubError("reauth", "For safety, sign in with Google again, then try once more", 401)

    async def find_account(login_name: str) -> Any:
        """The account a sign-in names: a username, or an email confirmed on it."""
        if "@" in login_name:
            return await db.user_by_email(login_name.lower()) if len(login_name) <= EMAIL_MAX else None
        return await db.user_by_name(login_name) if USERNAME_RE.fullmatch(login_name) else None

    async def second_factor(user: Any, code: str | None, lock_key: str) -> None:
        """When the account has an authenticator on, the code from it (or a backup code) is needed too."""
        row = await db.mfa(user.id)
        if row is None or row.enabled_at is None:
            return
        if not code or not code.strip():
            raise HubError("mfa_required", "Enter the code from your authenticator app", 401)
        secret = mfa.totp_secret(settings.secret_key, row.salt)
        step = mfa.check_totp(secret, code, time.time(), row.last_step)
        if step is not None and await db.use_step(user.id, step):
            return
        if await db.spend_backup(user.id, lambda h: mfa.take_backup_code(settings.secret_key, code, h)):
            return
        lockout.fail(lock_key)
        raise HubError("bad_code", "That code isn't right, or it was just used. Try the next one", 401)

    async def require_user(request: Request) -> Any:
        user = await current(request)
        if user is None:
            raise HubError("signed_out", "Sign in first", 401)
        return user

    # POST /api/auth/* is charged to this same bucket by the rate-limit middleware (security.py), so those
    # routes don't call this: one request, one token. The /api/me/* security actions call it.
    def throttle(request: Request) -> None:
        if not limiter.allow(ip(request)):
            raise HubError("rate_limited", "Too many tries. Wait a minute and try again", 429)

    @api.post(
        "/api/auth/signup", status_code=201, response_model=schemas.NewAccount, responses=schemas.ERRORS
    )
    async def signup(body: SignupBody, request: Request) -> JSONResponse:
        same_origin(request)
        need_db()
        username = clean_username(body.username)
        password = check_password(body.password, username)
        email = clean_email(body.email) if body.email and body.email.strip() else None
        code = new_recovery_code()
        pw = await asyncio.to_thread(hash_password, password)
        user = await db.create_user(username, pw, recovery_hash(settings.secret_key, code))
        if user is None:
            raise HubError("username_taken", "That username is taken", 409)
        if email:
            await db.set_email(user.id, email)
            user = await db.user_by_id(user.id)
            await send_verify(user, email, changed=False)
        resp = JSONResponse({"user": public_user(user), "recovery_code": code}, status_code=201)
        set_session(resp, await start_session(user.id, request))
        await signed_in(resp, request, user)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @api.post("/api/auth/login", response_model=schemas.UserBody, responses=schemas.ERRORS)
    async def login(body: LoginBody, request: Request) -> JSONResponse:
        same_origin(request)
        need_db()
        login_name = body.username.strip()
        user = await find_account(login_name)
        key = user.username_key if user is not None else login_name.casefold()  # one lock per account
        if lockout.locked(key):
            raise HubError("locked", "Too many wrong tries. Wait a minute and try again", 429)
        ok = await asyncio.to_thread(verify_password, body.password, user.pw_hash if user else DUMMY_HASH)
        if user is None or not ok:
            lockout.fail(key)
            raise HubError("bad_login", "Wrong username, email or password", 401)
        if suspended(user):  # told only after the right password, so it can't be probed
            until = aware(user.suspended_until).strftime("%d %b %Y")
            raise HubError("suspended", f"This account is suspended until {until}", 403)
        await second_factor(user, body.code, key)
        lockout.ok(key)
        resp = JSONResponse({"user": public_user(user)})
        set_session(resp, await start_session(user.id, request))
        await signed_in(resp, request, user)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @api.post("/api/auth/recover", response_model=schemas.NewAccount, responses=schemas.ERRORS)
    async def recover(body: RecoverBody, request: Request) -> JSONResponse:
        same_origin(request)
        need_db()
        key = "recover:" + body.username.strip().casefold()
        if lockout.locked(key):
            raise HubError("locked", "Too many wrong tries. Wait a minute and try again", 429)
        user = (
            await db.user_by_name(body.username.strip())
            if USERNAME_RE.fullmatch(body.username.strip())
            else None
        )
        given = recovery_hash(settings.secret_key, body.recovery_code)
        if user is None or not hmac.compare_digest(given, user.recovery_hash):
            lockout.fail(key)
            raise HubError("bad_recovery", "That username and recovery code don't match", 401)
        await second_factor(user, body.code, key)  # a recovery code resets the password, not this
        password = check_password(body.new_password, user.username)
        code = new_recovery_code()  # a used code is spent: here's the next one
        pw = await asyncio.to_thread(hash_password, password)
        await db.set_credentials(user.id, pw, recovery_hash(settings.secret_key, code))
        await db.delete_sessions(user.id)  # sign out everywhere else
        lockout.ok(key)
        lockout.ok(user.username_key)  # the lockout message points here, so a reset lifts it
        notice(
            user, "Your Snazzlebop password was reset", "Your recovery code was used to reset your password."
        )
        resp = JSONResponse({"user": public_user(user), "recovery_code": code})
        set_session(resp, await start_session(user.id, request))
        await signed_in(resp, request, user)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @api.post("/api/auth/logout", response_model=schemas.Ok, responses=schemas.ERRORS)
    async def logout(request: Request) -> JSONResponse:
        same_origin(request)
        token = request.cookies.get(SESSION_COOKIE)
        if token and len(token) <= 100 and db.ready:
            await db.delete_session(token_hash(token))
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(SESSION_COOKIE, path="/", samesite="strict", secure=settings.is_production)
        return resp

    @api.get("/api/me", response_model=schemas.Me)
    async def me(request: Request) -> JSONResponse:
        user = await current(request)
        return JSONResponse(
            {
                "user": public_user(user) if user else None,
                "accounts": bool(db.ready),
                "mail": mail.enabled,
                "google": google.enabled,
                "staff": user is not None and user.username_key in settings.staff_usernames,
            },
            headers={"Cache-Control": "no-store"},
        )

    @api.get("/api/me/stats", response_model=schemas.MyStats, responses=schemas.ERRORS)
    async def my_stats(request: Request) -> JSONResponse:
        user = await require_user(request)
        return JSONResponse(await db.user_stats(user.id, season_of()), headers={"Cache-Control": "no-store"})

    @api.get("/api/me/coins", response_model=schemas.CoinHistory, responses=schemas.ERRORS)
    async def my_coins(request: Request) -> JSONResponse:
        """Your balance, today's earnings toward the cap, and the latest changes."""
        user = await require_user(request)
        body = await db.coin_history(user.id)
        return JSONResponse({**body, "daily_cap": DAILY_COIN_CAP}, headers={"Cache-Control": "no-store"})

    @api.post("/api/me/password", response_model=schemas.Ok, responses=schemas.ERRORS)
    async def change_password(body: PasswordBody, request: Request) -> JSONResponse:
        same_origin(request)
        throttle(request)
        user = await require_user(request)
        await confirm(user, body.password, request, "Your current password isn't right")
        password = check_password(body.new_password, user.username)
        pw = await asyncio.to_thread(hash_password, password)
        await db.set_credentials(user.id, pw, None)
        await db.delete_sessions(user.id)
        notice(user, "Your Snazzlebop password was changed", "The password for your account was changed.")
        resp = JSONResponse({"ok": True})
        set_session(resp, await start_session(user.id, request))
        return resp

    @api.post("/api/me/delete", response_model=schemas.Ok, responses=schemas.ERRORS)
    async def delete_me(body: ConfirmBody, request: Request) -> JSONResponse:
        same_origin(request)
        throttle(request)
        user = await require_user(request)
        await confirm(user, body.password, request)
        await second_factor(user, body.code, "delete:" + user.username_key)
        tell(user, emails.goodbye(site, user.username), "goodbye")
        forget(user.id, await db.delete_user(user.id))  # presence: the account and clubs that closed
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(SESSION_COOKIE, path="/", samesite="strict", secure=settings.is_production)
        return resp

    # -- sign in with Google (oidc.py) ------------------------------------------------------------------
    STATE_COOKIE = "sb_oidc"

    def done(where: str) -> RedirectResponse:
        """Back to the account page with an outcome the page explains; the attempt's cookie goes."""
        resp = RedirectResponse(f"/account?google={where}", status_code=303)
        resp.delete_cookie(STATE_COOKIE, path="/api/auth/google")
        return resp

    def username_from(claims: dict[str, Any]) -> str:
        raw = str(claims.get("given_name") or str(claims.get("email", "")).split("@")[0] or "player")
        base = re.sub(r"[^A-Za-z0-9_.-]", "", unicodedata.normalize("NFKD", raw))[:14] or "player"
        if len(base) < 3:
            base = f"{base}_gg"
        return f"{base}_{secrets.randbelow(9000) + 1000}"

    @api.get("/api/auth/google/start", include_in_schema=False)
    async def google_start(request: Request, mode: str = "signin") -> RedirectResponse:
        """Off to Google. `mode=link` adds Google to the signed-in account instead."""
        if not google.enabled or not db.ready:
            return done("off")
        user = await current(request) if mode == "link" else None
        if mode == "link" and user is None:
            return done("signed_out")
        attempt = oidc.new_attempt("link" if user else "signin", user.id if user else None)
        resp = RedirectResponse(google.authorize(attempt), status_code=303)
        resp.set_cookie(
            STATE_COOKIE,
            box.seal(attempt),
            max_age=oidc.STATE_SECONDS,
            httponly=True,
            secure=settings.is_production,
            samesite="lax",  # Google's redirect back is a top-level navigation from another site
            path="/api/auth/google",
        )
        return resp

    @api.get("/api/auth/google/callback", include_in_schema=False)
    async def google_callback(
        request: Request, code: str = "", state: str = "", error: str = ""
    ) -> RedirectResponse:
        if not google.enabled or not db.ready:
            return done("off")
        if error:
            return done("cancelled")
        try:
            attempt = box.open(request.cookies.get(STATE_COOKIE, ""))
            if not state or not hmac.compare_digest(state, attempt.state) or not code or len(code) > 512:
                raise oidc.OidcError("state mismatch")
            claims = await asyncio.to_thread(google.claims, code, attempt)
        except oidc.OidcError as exc:
            log.warning("google sign-in refused: %s", exc)
            return done("failed")
        subject = str(claims["sub"])
        email = str(claims.get("email", "")).lower() if claims.get("email_verified") is True else ""

        if attempt.mode == "link":
            user = await db.user_by_id(attempt.user_id) if attempt.user_id else None
            if user is None or suspended(user):
                return done("failed")
            if not await db.add_identity(user.id, "google", subject, email):
                return done("taken")
            notice(
                user, "Google sign-in added to your Snazzlebop account", "You can now sign in with Google."
            )
            return done("linked")

        user = await db.identity_user("google", subject)
        outcome = "signed_in"
        if user is None:
            # Never matched to an existing account by email: that account links Google itself.
            if email and await db.user_by_email(email) is not None:
                return done("email_taken")
            hashed = recovery_hash(settings.secret_key, new_recovery_code())  # unused: Google is the way back
            for _ in range(5):
                user = await db.create_identity_user(
                    username_from(claims), hashed, "google", subject, email or None
                )
                if user is not None:
                    break
            if user is None:
                return done("failed")
            outcome = "welcome"
        if suspended(user):
            return done("suspended")
        row = await db.mfa(user.id)
        if row is not None and row.enabled_at is not None:
            # The authenticator still applies: finish on the sign-in-link page, which asks for the code.
            ticket = secrets.token_urlsafe(32)
            await db.add_token(token_hash(ticket), user.id, "login", "", GOOGLE_CODE_SECONDS)
            resp = RedirectResponse(f"/account/link#{ticket}", status_code=303)
            resp.delete_cookie(STATE_COOKIE, path="/api/auth/google")
            return resp
        resp = done(outcome)
        set_session(resp, await start_session(user.id, request))
        await signed_in(resp, request, user)
        return resp

    @api.get("/api/me/identities", response_model=schemas.Identities, responses=schemas.ERRORS)
    async def identities(request: Request) -> JSONResponse:
        user = await require_user(request)
        linked = {i.provider: i for i in await db.identities(user.id)}
        g = linked.get("google")
        body = {
            "google": {"email": g.email or None} if g is not None else None,
            "google_available": google.enabled,
            "has_password": bool(user.pw_hash),
        }
        return JSONResponse(body, headers={"Cache-Control": "no-store"})

    @api.post("/api/me/google/remove", response_model=schemas.Ok, responses=schemas.ERRORS)
    async def unlink_google(body: PasswordOnlyBody, request: Request) -> JSONResponse:
        same_origin(request)
        throttle(request)
        user = await require_user(request)
        if not user.pw_hash:
            raise HubError("needs_password", "Set a password first, or you'd have no way to sign in", 409)
        await confirm(user, body.password, request)
        await db.remove_identity(user.id, "google")
        notice(user, "Google sign-in removed from your Snazzlebop account", "Google sign-in was turned off.")
        return JSONResponse({"ok": True})

    # -- forgotten passwords by email, confirming an address -------------------------------------------
    BAD_LINK = "That link has expired or was already used. Ask for a new one"

    # -- signing in with a link sent to a confirmed email -----------------------------------------------
    @api.post("/api/auth/email-link", response_model=schemas.Ok, responses=schemas.ERRORS)
    async def email_link(body: EmailOnlyBody, request: Request) -> JSONResponse:
        """Email a one-time sign-in link to a confirmed address. The same answer whether or not an
        account has it, and at most one a minute per account."""
        same_origin(request)
        need_db()
        if not mail.enabled:
            raise HubError("mail_off", "Sign-in by email isn't set up here", 503)
        email = body.email.strip().lower()
        user = await db.user_by_email(email) if 3 <= len(email) <= EMAIL_MAX else None
        now = time.monotonic()
        if user is not None and not suspended(user) and now - link_sent.get(user.id, -1e9) > RESET_GAP:
            if len(link_sent) > 20000:
                link_sent.clear()  # memory bound; the per-IP limits still apply
            link_sent[user.id] = now
            token = secrets.token_urlsafe(32)
            await db.add_token(token_hash(token), user.id, "login", email, LINK_SECONDS)
            url = f"{site}/account/link#{token}"
            mail.send(email, emails.sign_in_link(site, user.username, url), "sign-in")
        return JSONResponse({"ok": True})

    @api.post("/api/auth/email-link/use", response_model=schemas.UserBody, responses=schemas.ERRORS)
    async def use_email_link(body: LinkBody, request: Request) -> JSONResponse:
        """The emailed link, opened. The authenticator step still applies when it's on; the link is
        only spent once everything checks out, so a missing code doesn't burn it."""
        same_origin(request)
        need_db()
        user = await db.peek_token(token_hash(body.token), "login") if len(body.token) >= 20 else None
        if user is None:
            raise HubError(
                "bad_link", "That sign-in link has expired or was already used. Ask for a new one", 400
            )
        if suspended(user):
            until = aware(user.suspended_until).strftime("%d %b %Y")
            raise HubError("suspended", f"This account is suspended until {until}", 403)
        await second_factor(user, body.code, user.username_key)
        if await db.take_token(token_hash(body.token), "login") is None:
            raise HubError(
                "bad_link", "That sign-in link has expired or was already used. Ask for a new one", 400
            )
        lockout.ok(user.username_key)
        resp = JSONResponse({"user": public_user(user)})
        set_session(resp, await start_session(user.id, request))
        await signed_in(resp, request, user)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @api.post("/api/auth/forgot", response_model=schemas.Ok, responses=schemas.ERRORS)
    async def forgot(body: ForgotBody, request: Request) -> JSONResponse:
        """Email a reset link. The same answer whether or not the account exists or has an email."""
        same_origin(request)
        need_db()
        if not mail.enabled:
            raise HubError(
                "mail_off", "Reset by email isn't set up here. Use your recovery code instead", 503
            )
        user = await find_account(body.login.strip())
        now = time.monotonic()
        if (
            user is not None
            and user.email
            and user.email_verified
            and now - reset_sent.get(user.id, -1e9) > RESET_GAP
        ):
            if len(reset_sent) > 20000:
                reset_sent.clear()  # memory bound; the per-IP limits still apply
            reset_sent[user.id] = now
            token = secrets.token_urlsafe(32)
            await db.add_token(token_hash(token), user.id, "reset", user.email, RESET_SECONDS)
            url = f"{site}/account/reset#{token}"
            mail.send(user.email, emails.reset_password(site, user.username, url), "reset")
        return JSONResponse({"ok": True})

    @api.post("/api/auth/reset", response_model=schemas.UserBody, responses=schemas.ERRORS)
    async def reset(body: ResetBody, request: Request) -> JSONResponse:
        same_origin(request)
        need_db()
        # Checked before the link is spent, so a weak password or a missing code doesn't burn it.
        user = await db.peek_token(token_hash(body.token), "reset") if len(body.token) >= 20 else None
        if user is None:
            raise HubError("bad_link", BAD_LINK, 400)
        password = check_password(body.new_password, user.username)
        await second_factor(user, body.code, "reset:" + user.username_key)
        if await db.take_token(token_hash(body.token), "reset") is None:
            raise HubError("bad_link", BAD_LINK, 400)
        pw = await asyncio.to_thread(hash_password, password)
        await db.set_credentials(user.id, pw, None)
        await db.delete_sessions(user.id)
        lockout.ok(user.username_key)
        notice(
            user, "Your Snazzlebop password was reset", "Your password was reset with a link we emailed you."
        )
        resp = JSONResponse({"user": public_user(user)})
        set_session(resp, await start_session(user.id, request))
        await signed_in(resp, request, user)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @api.post("/api/auth/verify", response_model=schemas.Ok, responses=schemas.ERRORS)
    async def verify(body: TokenBody, request: Request) -> JSONResponse:
        """The emailed confirmation link. Works signed in or out (it may open on another device)."""
        same_origin(request)
        need_db()
        taken = await db.take_token(token_hash(body.token), "verify") if len(body.token) >= 20 else None
        if taken is None:
            raise HubError("bad_link", BAD_LINK, 400)
        user, email = taken
        if not await db.confirm_email(user.id, email):
            raise HubError("email_taken", "That email is already confirmed on another account", 409)
        return JSONResponse({"ok": True})

    @api.post("/api/me/email", response_model=schemas.UserBody, responses=schemas.ERRORS)
    async def set_email(body: EmailBody, request: Request) -> JSONResponse:
        """Add or change the account's email: password first, then a confirmation link goes to it."""
        same_origin(request)
        throttle(request)
        user = await require_user(request)
        if not mail.enabled:
            raise HubError("mail_off", "Email isn't set up on this site", 503)
        await confirm(user, body.password, request)
        email = clean_email(body.email)
        if email == user.email and user.email_verified:
            raise HubError("same_email", "That's already your email")
        owner = await db.user_by_email(email)
        if owner is not None and owner.id != user.id:
            raise HubError("email_taken", "That email is already confirmed on another account", 409)
        if user.email and user.email_verified and user.email != email:
            mail.send(user.email, emails.email_changed(site, user.username, email), "email-changed")
        await db.set_email(user.id, email)
        fresh = await db.user_by_id(user.id)
        await send_verify(fresh, email, changed=True)
        return JSONResponse({"user": public_user(fresh)}, headers={"Cache-Control": "no-store"})

    @api.post("/api/me/email/resend", response_model=schemas.Ok, responses=schemas.ERRORS)
    async def resend(request: Request) -> JSONResponse:
        same_origin(request)
        throttle(request)
        user = await require_user(request)
        if not user.email:
            raise HubError("no_email", "Add an email first", 409)
        if user.email_verified:
            raise HubError("already_confirmed", "Your email is already confirmed", 409)
        await send_verify(user, user.email, changed=True)
        return JSONResponse({"ok": True})

    @api.post("/api/me/email/remove", response_model=schemas.UserBody, responses=schemas.ERRORS)
    async def remove_email(body: ConfirmBody, request: Request) -> JSONResponse:
        same_origin(request)
        throttle(request)
        user = await require_user(request)
        await confirm(user, body.password, request)
        notice(user, "Your Snazzlebop email was removed", "This email address was removed from your account.")
        await db.set_email(user.id, None)
        fresh = await db.user_by_id(user.id)
        return JSONResponse({"user": public_user(fresh)}, headers={"Cache-Control": "no-store"})

    @api.get("/api/me/sessions", response_model=schemas.SessionList, responses=schemas.ERRORS)
    async def my_sessions(request: Request) -> JSONResponse:
        """Every browser signed in to this account. Each is named by the first 12 characters of its
        hash: enough to pick one out, useless for signing in."""
        user = await require_user(request)
        mine = token_hash(request.cookies.get(SESSION_COOKIE, ""))
        rows = [
            {
                "id": s.token_hash[:12],
                "device": s.device or "A browser",
                "signed_in": aware(s.created_at).isoformat() if s.created_at else None,
                "last_seen": aware(s.last_seen).isoformat() if s.last_seen else None,
                "current": s.token_hash == mine,
            }
            for s in await db.user_sessions(user.id)
        ]
        return JSONResponse({"sessions": rows}, headers={"Cache-Control": "no-store"})

    @api.post("/api/me/sessions/{session_id}/revoke", response_model=schemas.Ok, responses=schemas.ERRORS)
    async def sign_out_one(session_id: str, request: Request) -> JSONResponse:
        same_origin(request)
        throttle(request)
        user = await require_user(request)
        if not re.fullmatch(r"[0-9a-f]{12}", session_id):
            raise HubError("bad_input", "Unknown device")
        if not await db.delete_session_by_prefix(user.id, session_id):
            raise HubError("no_session", "That device is already signed out", 404)
        return JSONResponse({"ok": True})

    @api.post("/api/me/sessions/revoke", response_model=schemas.Ok, responses=schemas.ERRORS)
    async def sign_out_others(request: Request) -> JSONResponse:
        """Sign out every other browser; this one stays signed in."""
        same_origin(request)
        throttle(request)
        user = await require_user(request)
        await db.delete_sessions(user.id, keep=token_hash(request.cookies.get(SESSION_COOKIE, "")))
        return JSONResponse({"ok": True})

    # Authenticator-app sign-in: set up (password first), confirm with a code, then every sign-in needs
    # a code. Backup codes stand in for a lost phone.
    @api.get("/api/me/mfa", response_model=schemas.MfaStatus, responses=schemas.ERRORS)
    async def mfa_status(request: Request) -> JSONResponse:
        user = await require_user(request)
        row = await db.mfa(user.id)
        on = row is not None and row.enabled_at is not None
        return JSONResponse(
            {"enabled": on, "backup_codes_left": len(row.backup_hashes or []) if on and row else 0},
            headers={"Cache-Control": "no-store"},
        )

    @api.post("/api/me/mfa/setup", response_model=schemas.MfaSetup, responses=schemas.ERRORS)
    async def mfa_setup(body: ConfirmBody, request: Request) -> JSONResponse:
        same_origin(request)
        throttle(request)
        user = await require_user(request)
        await confirm(user, body.password, request)
        row = await db.mfa(user.id)
        if row is not None and row.enabled_at is not None:
            raise HubError("mfa_on", "Your authenticator app is already set up", 409)
        salt = mfa.new_salt()
        await db.start_mfa(user.id, salt)
        secret = mfa.totp_secret(settings.secret_key, salt)
        uri = mfa.totp_uri(secret, user.username)
        return JSONResponse(
            {"secret": secret, "uri": uri, "qr": mfa.qr_matrix(uri)}, headers={"Cache-Control": "no-store"}
        )

    @api.post("/api/me/mfa/enable", response_model=schemas.BackupCodes, responses=schemas.ERRORS)
    async def mfa_enable(body: CodeBody, request: Request) -> JSONResponse:
        same_origin(request)
        throttle(request)
        user = await require_user(request)
        row = await db.mfa(user.id)
        if row is None or row.enabled_at is not None:
            raise HubError("no_setup", "Start the set-up first", 409)
        secret = mfa.totp_secret(settings.secret_key, row.salt)
        step = mfa.check_totp(secret, body.code, time.time(), row.last_step)
        if step is None or not await db.use_step(user.id, step):
            raise HubError("bad_code", "That code isn't right. Check the app and try the newest one", 401)
        codes, hashes = mfa.new_backup_codes(settings.secret_key)
        await db.enable_mfa(user.id, hashes)
        notice(
            user,
            "Authenticator app turned on for Snazzlebop",
            "Signing in now needs a code from your authenticator app (or a backup code).",
        )
        return JSONResponse({"codes": codes}, headers={"Cache-Control": "no-store"})

    @api.post("/api/me/mfa/disable", response_model=schemas.Ok, responses=schemas.ERRORS)
    async def mfa_disable(body: MfaOffBody, request: Request) -> JSONResponse:
        same_origin(request)
        throttle(request)
        user = await require_user(request)
        await confirm(user, body.password, request)
        await second_factor(user, body.code, "mfa:" + user.username_key)
        await db.delete_mfa(user.id)
        notice(
            user,
            "Authenticator app turned off for Snazzlebop",
            "Signing in no longer asks for a code from your authenticator app.",
        )
        return JSONResponse({"ok": True})

    @api.post("/api/me/mfa/backup-codes", response_model=schemas.BackupCodes, responses=schemas.ERRORS)
    async def mfa_new_codes(body: CodeBody, request: Request) -> JSONResponse:
        """A fresh set of backup codes; the old ones stop working."""
        same_origin(request)
        throttle(request)
        user = await require_user(request)
        row = await db.mfa(user.id)
        if row is None or row.enabled_at is None:
            raise HubError("mfa_off", "Set up your authenticator app first", 409)
        await second_factor(user, body.code, "mfa:" + user.username_key)
        codes, hashes = mfa.new_backup_codes(settings.secret_key)
        await db.set_backup_hashes(user.id, hashes)
        notice(
            user,
            "New Snazzlebop backup codes",
            "A new set of backup codes was made for your account. The old ones no longer work.",
        )
        return JSONResponse({"codes": codes}, headers={"Cache-Control": "no-store"})

    # Friends: add by username. A friend's open room shows only once both have added each other, so
    # adding someone never reveals where they are.
    async def friend_target(body: FriendBody, user: Any) -> Any:
        name = body.username.strip()
        other = await db.user_by_name(name) if USERNAME_RE.fullmatch(name) else None
        if other is None:
            raise HubError("no_such_user", "No account with that username", 404)
        if other.id == user.id:
            raise HubError("bad_friend", "That's you!")
        return other

    @api.get("/api/friends", response_model=schemas.Friends, responses=schemas.ERRORS)
    async def friends(request: Request) -> JSONResponse:
        user = await require_user(request)
        lists = await db.friends(user.id)
        ids = {i for i, _ in lists["mutual"]}
        rooms = hosting(ids)
        status = await status_of(ids) if status_of else {}
        return JSONResponse(
            {
                "friends": [
                    {"username": n, "room": rooms.get(i), "status": status.get(i, ("offline", None))[0]}
                    for i, n in lists["mutual"]
                ],
                "sent": [n for _, n in lists["sent"]],
                "asked": [n for _, n in lists["asked"]],
            },
            headers={"Cache-Control": "no-store"},
        )

    @api.post("/api/friends", response_model=schemas.Ok, responses=schemas.ERRORS)
    async def add_friend(body: FriendBody, request: Request) -> JSONResponse:
        same_origin(request)
        throttle(request)
        user = await require_user(request)
        other = await friend_target(body, user)
        if other.id in await db.block_set(user.id):
            raise HubError("cant_add", "You can't add that person", 403)
        if not await db.add_friend(user.id, other.id):
            raise HubError("friends_full", "Your friends list is full")
        return JSONResponse({"ok": True})

    @api.post("/api/friends/remove", response_model=schemas.Ok, responses=schemas.ERRORS)
    async def remove_friend(body: FriendBody, request: Request) -> JSONResponse:
        same_origin(request)
        user = await require_user(request)
        other = await friend_target(body, user)
        await db.remove_friend(user.id, other.id)
        return JSONResponse({"ok": True})

    @api.get("/api/shop", response_model=schemas.Shop)
    async def shop() -> dict[str, Any]:
        """Each game's own power-ups, for casual rooms (never ranked games or battles)."""
        items = []
        for cls in REGISTRY.values():
            for item, info in cls.POWERS.items():
                if item in GAME_POWER_PRICES:
                    items.append({"id": item, "price": GAME_POWER_PRICES[item], "game": cls.title, **info})
        for item, info in partylib.ITEMS.items():
            items.append({"id": item, "price": PARTY_PRICES[item], "game": "Party: any game", **info})
        for item, pack in partylib.EMOTES.items():
            emoji = " ".join(pack["emoji"])  # type: ignore[arg-type]
            text = f"{emoji} in your live reactions, in every room. Yours to keep"
            items.append(
                {
                    "id": item,
                    "price": EMOTE_PRICES[item],
                    "game": "Emotes",
                    "name": pack["name"],
                    "icon": pack["icon"],
                    "text": text,
                }
            )
        return {"items": items}

    @api.post("/api/shop/buy", response_model=schemas.UserBody, responses=schemas.ERRORS)
    async def buy(body: BuyBody, request: Request) -> JSONResponse:
        same_origin(request)
        user = await require_user(request)
        price = GAME_POWER_PRICES.get(body.item) or PARTY_PRICES.get(body.item) or EMOTE_PRICES.get(body.item)
        if price is None:
            raise HubError("bad_item", "That's not in the shop")
        if body.item in EMOTE_PRICES and (user.powerups or {}).get(body.item):
            raise HubError("owned", "You have that emote pack already")
        updated = await db.buy(user.id, body.item, price)
        if updated is None:
            raise HubError("not_enough_coins", "Not enough coins for that yet")
        return JSONResponse({"user": public_user(updated)}, headers={"Cache-Control": "no-store"})

    @api.get("/api/leaderboard", response_model=schemas.Leaderboard)
    async def leaderboard() -> JSONResponse:
        season = season_of()
        rows = await db.leaderboard(season, 10) if db.ready else []
        return JSONResponse({"season": season, "rows": rows}, headers={"Cache-Control": "no-store"})

    return api
