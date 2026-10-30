"""Snazzlebop Plus and ads over HTTP (rules in billing.py).

- GET /api/billing/config: what the browser needs (Paddle's client token and the Plus price id, the
  AdSense ids), or that payments and ads are off.
- POST /api/billing/checkout: a signed reference to your account for Paddle's checkout.
- POST /api/billing/paddle: Paddle's webhooks, the only thing that turns Plus on or pays its perks.
- GET /api/me/plus, POST /api/me/plus/manage: your Plus, and a link to Paddle's page to change or
  cancel it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.request
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import billing, schemas
from .accounts import check_same_origin, session_user
from .config import Settings
from .db import aware
from .rooms import HubError

log = logging.getLogger("snazzlebop.plus")

CUSTOMER_RE = re.compile(r"^ctm_[a-z0-9]{10,40}$")
SUBSCRIPTION_EVENTS = {
    "subscription.created",
    "subscription.activated",
    "subscription.updated",
    "subscription.canceled",
    "subscription.past_due",
    "subscription.paused",
    "subscription.resumed",
    "subscription.trialing",
}


def _api_base(settings: Settings) -> str:
    return (
        "https://api.paddle.com" if settings.paddle_env == "production" else "https://sandbox-api.paddle.com"
    )


def _portal(settings: Settings, customer_id: str) -> str | None:
    """Paddle's customer portal for one customer (Paddle's API; blocking, run in a thread)."""
    req = urllib.request.Request(  # noqa: S310 - a fixed https URL
        f"{_api_base(settings)}/customers/{customer_id}/portal-sessions",
        data=b"{}",
        method="POST",
        headers={"Authorization": f"Bearer {settings.paddle_api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310  # nosec B310
            body = json.loads(r.read())
        url = body["data"]["urls"]["general"]["overview"]
        return url if isinstance(url, str) and url.startswith("https://") else None
    except Exception:
        log.warning("could not open the customer portal")
        return None


def _prices(data: dict[str, Any]) -> set[str]:
    return {
        str(i.get("price", {}).get("id", ""))
        for i in data.get("items", []) or []
        if isinstance(i, dict) and isinstance(i.get("price"), dict)
    }


def router(settings: Settings, db: Any) -> APIRouter:
    api = APIRouter()

    async def me(request: Request) -> Any:
        if not db.ready:
            raise HubError("accounts_down", "Accounts are unavailable right now. Games still work!", 503)
        user = await session_user(request, db)
        if user is None:
            raise HubError("signed_out", "Sign in first", 401)
        return user

    @api.get("/api/billing/config", response_model=schemas.BillingConfig)
    async def config() -> JSONResponse:
        on = billing.payments_on(settings) and db.ready
        body = {
            "payments": on,
            "environment": settings.paddle_env,
            "client_token": settings.paddle_client_token if on else "",
            "plus_price": settings.paddle_plus_price if on else "",
            "ads": {"client": settings.adsense_client, "slot": settings.adsense_slot}
            if billing.ads_on(settings)
            else None,
            "perks": {"coins": billing.PLUS_COINS, "items": dict(billing.PLUS_ITEMS)},
        }
        return JSONResponse(body, headers={"Cache-Control": "no-store"})

    @api.post("/api/billing/checkout", response_model=schemas.PlusCheckout, responses=schemas.ERRORS)
    async def checkout(request: Request) -> JSONResponse:
        check_same_origin(request, settings)
        user = await me(request)
        if not billing.payments_on(settings):
            raise HubError("payments_off", "Plus isn't on sale here yet", 503)
        body = {
            "price": settings.paddle_plus_price,
            "custom_data": billing.account_ref(settings, user.id),
            "email": user.email if user.email_verified else None,
        }
        return JSONResponse(body, headers={"Cache-Control": "no-store"})

    @api.post("/api/billing/paddle", response_model=schemas.Ok, responses=schemas.ERRORS)
    async def paddle_webhook(request: Request) -> JSONResponse:
        """Paddle's signed notifications. Anything unsigned, stale or about someone else is refused."""
        raw = await request.body()
        if not billing.verify(
            settings.paddle_webhook_secret, request.headers.get("paddle-signature", ""), raw
        ):
            raise HubError("bad_signature", "Not signed by Paddle", 401)
        if not db.ready:
            raise HubError("accounts_down", "Try again later", 503)  # Paddle retries
        try:
            event = json.loads(raw)
            kind, event_id, data = str(event["event_type"]), str(event["event_id"]), event["data"]
            if not isinstance(data, dict):
                raise ValueError(kind)
        except Exception:
            raise HubError("bad_event", "Not a Paddle event", 400) from None
        sub_id = data.get("id")
        if kind in SUBSCRIPTION_EVENTS and isinstance(sub_id, str) and sub_id.startswith("sub_"):
            user_id = billing.account_of(settings, data.get("custom_data")) or await db.subscription_user(
                sub_id
            )
            if user_id is not None and settings.paddle_plus_price in _prices(data):
                period = data.get("current_billing_period")
                period = period if isinstance(period, dict) else {}
                await db.set_subscription(
                    sub_id,
                    user_id,
                    str(data.get("customer_id") or ""),
                    str(data.get("status") or ""),
                    billing.parse_time(period.get("ends_at")),
                    billing.parse_time(event.get("occurred_at")) or datetime.now(UTC),
                )
        elif kind == "transaction.completed" and data.get("subscription_id"):
            user_id = billing.account_of(settings, data.get("custom_data")) or await db.subscription_user(
                str(data["subscription_id"])
            )
            if user_id is not None and settings.paddle_plus_price in _prices(data):
                await db.grant_plus_month(user_id, str(data.get("id", event_id)))
        else:
            user_id = None
        await db.billing_seen(event_id, kind, user_id)
        return JSONResponse({"ok": True})

    @api.get("/api/billing/app-user", response_model=schemas.AppUser, responses=schemas.ERRORS)
    async def app_user(request: Request) -> JSONResponse:
        """The id the store app gives RevenueCat for a purchase: this account, signed by this server."""
        user = await me(request)
        return JSONResponse(
            {"app_user_id": billing.app_user_id(settings, user.id)}, headers={"Cache-Control": "no-store"}
        )

    @api.post("/api/billing/revenuecat", response_model=schemas.Ok, responses=schemas.ERRORS)
    async def revenuecat_webhook(request: Request) -> JSONResponse:
        """Plus bought in the apps (App Store, Google Play), as RevenueCat reports it. Refused without the
        shared Authorization value; only accounts this server signed can be credited."""
        if not billing.revenuecat_ok(settings, request.headers.get("authorization", "")):
            raise HubError("bad_signature", "Not from RevenueCat", 401)
        if not db.ready:
            raise HubError("accounts_down", "Try again later", 503)  # RevenueCat retries
        try:
            event = json.loads(await request.body())["event"]
            kind, event_id = str(event["type"]), str(event["id"])
        except Exception:
            raise HubError("bad_event", "Not a RevenueCat event", 400) from None
        store = billing.STORES.get(str(event.get("store", "")))
        status = billing.store_status(kind)
        ids = [event.get("app_user_id"), event.get("original_app_user_id"), *(event.get("aliases") or [])]
        user_id = next((u for u in (billing.account_of_app_user(settings, i) for i in ids) if u), None)
        wants_plus = settings.revenuecat_entitlement in (event.get("entitlement_ids") or [])
        original = str(event.get("original_transaction_id") or "")
        if store and status and user_id is not None and wants_plus and original:
            ends = event.get("expiration_at_ms")
            period_end = datetime.fromtimestamp(ends / 1000, UTC) if isinstance(ends, int | float) else None
            at_ms = event.get("event_timestamp_ms")
            at = (
                datetime.fromtimestamp(at_ms / 1000, UTC)
                if isinstance(at_ms, int | float)
                else datetime.now(UTC)
            )
            await db.set_subscription(f"{store}:{original}", user_id, "", status, period_end, at)
            if kind in ("INITIAL_PURCHASE", "RENEWAL") and event.get("transaction_id"):
                await db.grant_plus_month(user_id, f"{store}:{event['transaction_id']}")
        else:
            user_id = None
        await db.billing_seen(f"rc:{event_id}", kind, user_id)
        return JSONResponse({"ok": True})

    @api.get("/api/me/plus", response_model=schemas.MyPlus, responses=schemas.ERRORS)
    async def my_plus(request: Request) -> JSONResponse:
        user = await me(request)
        sub = await db.my_subscription(user.id)
        body = {
            "active": billing.has_plus(user),
            "gift": billing.is_friend(user) and not billing.is_plus(user.plus_until),
            "until": aware(user.plus_until).isoformat() if user.plus_until else None,
            "status": sub.status if sub is not None else None,
            "can_manage": bool(sub is not None and sub.customer_id and settings.paddle_api_key),
            "source": None if sub is None else sub.id.split(":", 1)[0] if ":" in sub.id else "paddle",
        }
        return JSONResponse(body, headers={"Cache-Control": "no-store"})

    @api.post("/api/me/plus/manage", response_model=schemas.PlusManage, responses=schemas.ERRORS)
    async def manage(request: Request) -> JSONResponse:
        """A one-time link to Paddle's page for your subscription: change the card, or cancel."""
        check_same_origin(request, settings)
        user = await me(request)
        sub = await db.my_subscription(user.id)
        if sub is None or not CUSTOMER_RE.match(sub.customer_id) or not settings.paddle_api_key:
            raise HubError("no_subscription", "There's no subscription to manage", 404)
        url = await asyncio.to_thread(_portal, settings, sub.customer_id)
        if url is None:
            raise HubError("portal_down", "Paddle didn't answer: try again in a minute", 502)
        return JSONResponse({"url": url}, headers={"Cache-Control": "no-store"})

    return api
