"""Payments (Paddle) and ads (Google AdSense). Off unless configured.

Paddle is the merchant of record: it sells Snazzlebop Plus to buyers worldwide in their own currency
(cards, PayPal, Apple Pay, Google Pay, UPI and more), and handles sales tax and VAT. The site never sees
card details: Paddle.js opens Paddle's own checkout. What the server trusts is only Paddle's signed
webhooks: a checkout can't grant anything by itself.

- Checkout carries `custom_data` with the account id and an HMAC of it (signed here), so a webhook can
  only ever credit the account that started that checkout.
- Every webhook is checked against PADDLE_WEBHOOK_SECRET (HMAC-SHA256 over "ts:body", with a time
  limit), recorded once by its event id (a resend changes nothing), and the month's perks are paid
  once per billing period through the coin ledger.

Plus: no ads, coins and a few party items each month, every emote pack while it lasts, and a badge. Ads only
show on the lobby and results screens, never during a game and never to Plus members.
Pure apart from the signature helpers (stdlib only).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from .config import Settings

PLUS_COINS = 300  # each paid month
PLUS_ITEMS = {"party_confetti": 2, "party_airhorn": 1, "party_replay": 1}  # each paid month
GRACE = timedelta(days=1)  # Plus stays on this long past a period's end while a renewal goes through
SIGNATURE_AGE = 300  # seconds a webhook signature stays acceptable

# Where Paddle.js and its checkout live (Content Security Policy, only when payments are on).
PADDLE_SCRIPT = ("https://cdn.paddle.com",)
PADDLE_FRAMES = ("https://buy.paddle.com", "https://sandbox-buy.paddle.com")
PADDLE_CONNECT = ("https://*.paddle.com",)
# Google AdSense (only when ads are on). Ads run third-party script: this is the one reviewed exception.
ADS_HOSTS = (
    "https://pagead2.googlesyndication.com",
    "https://*.googlesyndication.com",
    "https://*.doubleclick.net",
    "https://*.google.com",
    "https://*.gstatic.com",
    "https://*.googleadservices.com",
)


def payments_on(settings: Settings) -> bool:
    return bool(
        settings.paddle_client_token and settings.paddle_webhook_secret and settings.paddle_plus_price
    )


def ads_on(settings: Settings) -> bool:
    return bool(settings.adsense_client and settings.adsense_slot)


def account_ref(settings: Settings, user_id: int) -> dict[str, str]:
    """custom_data for a checkout: the account and a signature only this server can make."""
    acct = str(user_id)
    sig = hmac.new(settings.secret_key.encode(), f"plus:{acct}".encode(), hashlib.sha256).hexdigest()[:32]
    return {"account": acct, "sig": sig}


def account_of(settings: Settings, custom: object) -> int | None:
    """The account a webhook's custom_data names, if its signature is ours."""
    if not isinstance(custom, dict):
        return None
    acct, sig = custom.get("account"), custom.get("sig")
    if not isinstance(acct, str) or not acct.isdigit() or not isinstance(sig, str):
        return None
    if not hmac.compare_digest(account_ref(settings, int(acct))["sig"], sig):
        return None
    return int(acct)


def verify(secret: str, header: str, body: bytes, now: float | None = None) -> bool:
    """Paddle-Signature: "ts=<unix>;h1=<hex>" (more than one h1 while a secret is being rotated)."""
    if not secret or not header:
        return False
    parts = [p.split("=", 1) for p in header.split(";") if "=" in p]
    ts = next((v for k, v in parts if k == "ts"), "")
    sigs = [v for k, v in parts if k == "h1"]
    if not ts.isdigit() or not sigs:
        return False
    if abs((now if now is not None else time.time()) - int(ts)) > SIGNATURE_AGE:
        return False
    want = hmac.new(secret.encode(), ts.encode() + b":" + body, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(want, s) for s in sigs)


def plus_until(status: str, period_end: datetime | None, now: datetime) -> datetime | None:
    """How long Plus lasts after a subscription event. Paid time is kept after a cancel; a paused one
    stops now."""
    if status in ("active", "trialing", "past_due", "canceled") and period_end is not None:
        return period_end + (GRACE if status in ("active", "trialing", "past_due") else timedelta(0))
    if status == "paused":
        return now
    return None


def is_plus(until: datetime | None, now: datetime | None = None) -> bool:
    return until is not None and _aware(until) > (now or datetime.now(UTC))


# Confirmed email addresses that have Plus without paying (PLUS_FRIENDS), set once at startup.
_friends: frozenset[str] = frozenset()


def set_friends(emails: Iterable[str]) -> None:
    global _friends
    _friends = frozenset(e.lower() for e in emails)


def is_friend(user: Any) -> bool:
    """On the friends list, by an address the account has confirmed (an unconfirmed one proves nothing)."""
    email = getattr(user, "email", None)
    return bool(_friends and email and getattr(user, "email_verified", False) and email.lower() in _friends)


def has_plus(user: Any, now: datetime | None = None) -> bool:
    """Plus for everything a member gets (no ads, emote packs, the badge): paid, or on the friends list.
    The monthly coins and items still come only with a paid month."""
    return is_plus(getattr(user, "plus_until", None), now) or is_friend(user)


def parse_time(raw: object) -> datetime | None:
    """Paddle's RFC 3339 times ("2026-11-26T10:00:00.000000Z")."""
    if not isinstance(raw, str):
        return None
    try:
        return _aware(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError:
        return None


def _aware(when: datetime) -> datetime:
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def csp_hosts(settings: Settings) -> dict[str, tuple[str, ...]]:
    """The hosts the page may load from, for what's configured (nothing: all same-origin)."""
    out: dict[str, tuple[str, ...]] = {"script": (), "frame": (), "connect": (), "img": ()}
    if payments_on(settings):
        out["script"] += PADDLE_SCRIPT
        out["frame"] += PADDLE_FRAMES
        out["connect"] += PADDLE_CONNECT
    if ads_on(settings):
        out["script"] += ADS_HOSTS
        out["frame"] += ADS_HOSTS
        out["connect"] += ADS_HOSTS
        out["img"] += ("https:",)  # ad creatives come from anywhere an advertiser hosts them
    return out
