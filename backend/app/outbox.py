"""The outbox worker: delivers queued events to their destinations ("sinks"), at least once.

Each change that other systems should hear about is queued in the outbox table in the same transaction
as the change (db._record). This worker picks up due items, hands each to its sink, and marks it done;
a failure is retried with growing waits (30 s, 1 min, 2 min ... capped at an hour), and after
MAX_ATTEMPTS it is marked failed and kept for a person to look at. Delivery is at least once:
receivers de-duplicate on the delivery id (X-Snazzlebop-Delivery).

A sink is anything with `name` and `deliver(topic, delivery_id, payload)`. Today there is a signed
webhook; a Jira, Slack or AI-triage sink is one more class registered in `sinks_for`, with no change to
the code that produces events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from .config import Settings
from .events import sign

log = logging.getLogger("snazzlebop.outbox")
MAX_ATTEMPTS = 10
BATCH = 20
POLL_SECONDS = 2.0
TIMEOUT = 10.0


class Sink(Protocol):
    name: str

    def deliver(self, topic: str, delivery_id: int, payload: dict[str, Any]) -> None:
        """Send one event. Blocking (it runs in a thread); raise on any failure."""
        ...


class WebhookSink:
    """POSTs each event as JSON to a URL the operator configured, signed so the receiver can trust it:
    X-Snazzlebop-Signature = sha256=HMAC(secret, "<timestamp>.<body>")."""

    name = "webhook"

    def __init__(self, url: str, secret: str) -> None:
        self.url, self.secret = url, secret

    def deliver(self, topic: str, delivery_id: int, payload: dict[str, Any]) -> None:
        body = json.dumps(
            {"id": delivery_id, "topic": topic, "data": payload}, separators=(",", ":"), ensure_ascii=False
        ).encode()
        stamp = str(int(time.time()))
        req = urllib.request.Request(  # noqa: S310 - an https URL the operator configured
            self.url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Snazzlebop-Webhooks/1",
                "X-Snazzlebop-Event": topic,
                "X-Snazzlebop-Delivery": str(delivery_id),
                "X-Snazzlebop-Timestamp": stamp,
                "X-Snazzlebop-Signature": sign(self.secret, stamp, body),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310  # nosec B310
                resp.read(1024)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"webhook status {exc.code}") from None


def sinks_for(settings: Settings) -> dict[str, Sink]:
    """The destinations switched on by configuration."""
    out: dict[str, Sink] = {}
    if settings.report_webhook_url:
        out["webhook"] = WebhookSink(settings.report_webhook_url, settings.report_webhook_secret)
    return out


def backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(30 * 2 ** (attempts - 1), 3600))


class Outbox:
    def __init__(self, db: Any, sinks: dict[str, Sink], clock: Callable[[], datetime] | None = None) -> None:
        self.db = db
        self.sinks = sinks
        self.clock = clock or (lambda: datetime.now(UTC))

    @property
    def names(self) -> list[str]:
        """Where new events go (written into the outbox with each change)."""
        return list(self.sinks)

    async def run_once(self) -> int:
        """Deliver what's due. Returns how many items were handled."""
        items = await self.db.outbox_due(BATCH)
        for item in items:
            sink = self.sinks.get(item.sink)
            if sink is None:  # a destination switched off since: keep it, but stop trying
                await self.db.outbox_retry(item.id, item.attempts, None, "sink not configured")
                continue
            try:
                await asyncio.to_thread(sink.deliver, item.topic, item.id, item.payload)
            except Exception as exc:  # noqa: BLE001 - any failure is retried, never raised
                attempts = item.attempts + 1
                retry_at = self.clock() + backoff(attempts) if attempts < MAX_ATTEMPTS else None
                await self.db.outbox_retry(item.id, attempts, retry_at, f"{type(exc).__name__}: {exc}")
                log.warning("outbox: %s delivery %d failed (%d)", item.sink, item.id, attempts)
            else:
                await self.db.outbox_done(item.id)
        return len(items)

    async def run(self) -> None:
        """The background loop (main.py's lifespan). Quiet when there's nothing to send."""
        while True:
            try:
                if self.sinks and self.db.ready:
                    await self.run_once()
            except Exception:  # noqa: BLE001 - the loop must survive a database hiccup
                log.exception("outbox loop")
            await asyncio.sleep(POLL_SECONDS)
