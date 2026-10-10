"""Accounts, coins and power-ups.

Sign-up is a username and a password; there is no email. Instead you get a one-time recovery code
(shown once, stored only as a keyed hash) that resets a forgotten password.

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
import re
import secrets
import time
import unicodedata
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import HTTPConnection

from .coins import POWERUP_PRICES, season_of
from .config import Settings
from .rooms import HubError
from .security import RateLimiter, client_ip
from .show import CARDS

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


# -- validation --------------------------------------------------------------------------------------
def clean_username(raw: object) -> str:
    if not isinstance(raw, str):
        raise HubError("bad_username", "Usernames are 3-20 letters, numbers, dots, dashes or underscores")
    name = unicodedata.normalize("NFKC", raw).strip()
    if not USERNAME_RE.fullmatch(name):
        raise HubError("bad_username", "Usernames are 3-20 letters, numbers, dots, dashes or underscores")
    return name


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


class LoginBody(SignupBody):
    pass


class RecoverBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(max_length=64)
    recovery_code: str = Field(max_length=64)
    new_password: str = Field(max_length=PASSWORD_MAX)


class PasswordBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(max_length=PASSWORD_MAX)
    new_password: str = Field(max_length=PASSWORD_MAX)


class ConfirmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(max_length=PASSWORD_MAX)


class BuyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str = Field(max_length=16)


def public_user(user: Any) -> dict[str, Any]:
    return {"username": user.username, "coins": user.coins, "powerups": dict(user.powerups or {})}


async def session_user(request: HTTPConnection, db: Any) -> Any:
    """The signed-in account behind this request's (or WebSocket's) cookie, or None."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token or len(token) > 100 or not db.ready:
        return None
    return await db.user_for_session(token_hash(token))


def router(settings: Settings, db: Any, limiter: RateLimiter) -> APIRouter:
    api = APIRouter()
    lockout = Lockout()

    def ip(request: Request) -> str:
        return client_ip(request.scope, settings.trusted_proxy_hops, settings.client_ip_header)

    def same_origin(request: Request) -> None:
        """No cross-site writes: the browser's Origin must be ours (SameSite=Strict backs this up)."""
        origin = request.headers.get("origin")
        if origin is None:
            if settings.is_production:
                raise HubError("bad_origin", "That request came from the wrong place", 403)
            return
        if origin not in settings.allowed_origins:
            raise HubError("bad_origin", "That request came from the wrong place", 403)

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

    async def start_session(user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        await db.create_session(token_hash(token), user_id, SESSION_DAYS * 86400)
        return token

    async def current(request: Request) -> Any:
        return await session_user(request, db)

    async def require_user(request: Request) -> Any:
        user = await current(request)
        if user is None:
            raise HubError("signed_out", "Sign in first", 401)
        return user

    def throttle(request: Request) -> None:
        if not limiter.allow(ip(request)):
            raise HubError("rate_limited", "Too many tries. Wait a minute and try again", 429)

    @api.post("/api/auth/signup", status_code=201)
    async def signup(body: SignupBody, request: Request) -> JSONResponse:
        same_origin(request)
        throttle(request)
        need_db()
        username = clean_username(body.username)
        password = check_password(body.password, username)
        code = new_recovery_code()
        pw = await asyncio.to_thread(hash_password, password)
        user = await db.create_user(username, pw, recovery_hash(settings.secret_key, code))
        if user is None:
            raise HubError("username_taken", "That username is taken", 409)
        resp = JSONResponse({"user": public_user(user), "recovery_code": code}, status_code=201)
        set_session(resp, await start_session(user.id))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @api.post("/api/auth/login")
    async def login(body: LoginBody, request: Request) -> JSONResponse:
        same_origin(request)
        throttle(request)
        need_db()
        key = body.username.strip().casefold()
        if lockout.locked(key):
            raise HubError("locked", "Too many wrong tries. Wait a minute and try again", 429)
        user = (
            await db.user_by_name(body.username.strip())
            if USERNAME_RE.fullmatch(body.username.strip())
            else None
        )
        ok = await asyncio.to_thread(verify_password, body.password, user.pw_hash if user else DUMMY_HASH)
        if user is None or not ok:
            lockout.fail(key)
            raise HubError("bad_login", "Wrong username or password", 401)
        lockout.ok(key)
        resp = JSONResponse({"user": public_user(user)})
        set_session(resp, await start_session(user.id))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @api.post("/api/auth/recover")
    async def recover(body: RecoverBody, request: Request) -> JSONResponse:
        same_origin(request)
        throttle(request)
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
        password = check_password(body.new_password, user.username)
        code = new_recovery_code()  # a used code is spent: here's the next one
        pw = await asyncio.to_thread(hash_password, password)
        await db.set_credentials(user.id, pw, recovery_hash(settings.secret_key, code))
        await db.delete_sessions(user.id)  # sign out everywhere else
        lockout.ok(key)
        resp = JSONResponse({"user": public_user(user), "recovery_code": code})
        set_session(resp, await start_session(user.id))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @api.post("/api/auth/logout")
    async def logout(request: Request) -> JSONResponse:
        same_origin(request)
        token = request.cookies.get(SESSION_COOKIE)
        if token and len(token) <= 100 and db.ready:
            await db.delete_session(token_hash(token))
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(SESSION_COOKIE, path="/", samesite="strict", secure=settings.is_production)
        return resp

    @api.get("/api/me")
    async def me(request: Request) -> JSONResponse:
        user = await current(request)
        return JSONResponse(
            {"user": public_user(user) if user else None, "accounts": bool(db.ready)},
            headers={"Cache-Control": "no-store"},
        )

    @api.get("/api/me/stats")
    async def my_stats(request: Request) -> JSONResponse:
        user = await require_user(request)
        return JSONResponse(await db.user_stats(user.id, season_of()), headers={"Cache-Control": "no-store"})

    @api.post("/api/me/password")
    async def change_password(body: PasswordBody, request: Request) -> JSONResponse:
        same_origin(request)
        throttle(request)
        user = await require_user(request)
        if not await asyncio.to_thread(verify_password, body.password, user.pw_hash):
            raise HubError("bad_login", "Your current password isn't right", 401)
        password = check_password(body.new_password, user.username)
        pw = await asyncio.to_thread(hash_password, password)
        await db.set_credentials(user.id, pw, None)
        await db.delete_sessions(user.id)
        resp = JSONResponse({"ok": True})
        set_session(resp, await start_session(user.id))
        return resp

    @api.post("/api/me/delete")
    async def delete_me(body: ConfirmBody, request: Request) -> JSONResponse:
        same_origin(request)
        throttle(request)
        user = await require_user(request)
        if not await asyncio.to_thread(verify_password, body.password, user.pw_hash):
            raise HubError("bad_login", "That password isn't right", 401)
        await db.delete_user(user.id)
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(SESSION_COOKIE, path="/", samesite="strict", secure=settings.is_production)
        return resp

    @api.get("/api/shop")
    async def shop() -> dict[str, Any]:
        return {"items": [{"id": k, "price": v, **CARDS[k]} for k, v in POWERUP_PRICES.items()]}

    @api.post("/api/shop/buy")
    async def buy(body: BuyBody, request: Request) -> JSONResponse:
        same_origin(request)
        user = await require_user(request)
        if body.item not in POWERUP_PRICES:
            raise HubError("bad_item", "That's not in the shop")
        updated = await db.buy(user.id, body.item, POWERUP_PRICES[body.item])
        if updated is None:
            raise HubError("not_enough_coins", "Not enough coins for that yet")
        return JSONResponse({"user": public_user(updated)}, headers={"Cache-Control": "no-store"})

    @api.get("/api/leaderboard")
    async def leaderboard() -> JSONResponse:
        season = season_of()
        rows = await db.leaderboard(season, 10) if db.ready else []
        return JSONResponse({"season": season, "rows": rows}, headers={"Cache-Control": "no-store"})

    return api
