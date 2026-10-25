"""Notifications: every one is written to the person's inbox first, then pushed to their devices when
the rules allow.

Rules, per person:
- Each kind can be switched off (then nothing is sent, not even to the inbox), and a club can be muted.
- Daily limits per kind (rolling 24 hours): a club game filling up at most 3 a day per club, invites
  at most 10 a day. Past the limit nothing more is sent.
- Grouping: a notification with a group key replaces an unread one with the same key from the last
  few hours ("4 people from Hostel 4 want to play Imposter", never 4 notifications).
- Pushes (not the inbox) wait for quiet hours to end: the person's own and the club's both count,
  in the person's local time. At most PUSH_CAP pushes a day in all.
Pushes go out in the background; a subscription the push service says is gone is deleted.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from . import webpush
from .config import Settings

log = logging.getLogger("snazzlebop.notify")

KINDS = {
    # kind: (label for settings, limit per 24 hours, is the limit per club)
    "club_up": ("A club game is filling up", 3, True),
    "invite": ("A friend or club member invites you to a room", 10, False),
    "battle": ("A club member challenges you to a battle", 10, False),
}
PUSH_CAP = 8
GROUP_HOURS = 6
MAX_PENDING = 500
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DEFAULT_PREFS: dict[str, Any] = {
    "hidden": False,  # appear offline
    "types": {k: True for k in KINDS},
    "quiet": None,  # {"from": "23:00", "to": "08:00"}, in local time
    "tz": 0,  # minutes east of UTC, sent by the app
    "muted_clubs": [],
}


class PrefsError(ValueError):
    pass


def clean_prefs(raw: Any, current: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge a partial update into the current settings, refusing anything malformed."""
    prefs = merged(current)
    if not isinstance(raw, dict) or set(raw) - {"hidden", "types", "quiet", "tz"}:
        raise PrefsError("Unknown setting")
    if "hidden" in raw:
        if not isinstance(raw["hidden"], bool):
            raise PrefsError("hidden must be on or off")
        prefs["hidden"] = raw["hidden"]
    if "types" in raw:
        types = raw["types"]
        if (
            not isinstance(types, dict)
            or set(types) - set(KINDS)
            or not all(isinstance(v, bool) for v in types.values())
        ):
            raise PrefsError("Unknown notification type")
        prefs["types"] = {**prefs["types"], **types}
    if "quiet" in raw:
        quiet = raw["quiet"]
        if quiet is not None:
            ok = isinstance(quiet, dict) and set(quiet) == {"from", "to"}
            if not ok or not all(isinstance(quiet[k], str) and _TIME.match(quiet[k]) for k in ("from", "to")):
                raise PrefsError("Quiet hours are two times like 23:00 and 08:00")
            if quiet["from"] == quiet["to"]:
                raise PrefsError("Quiet hours must start and end at different times")
        prefs["quiet"] = quiet
    if "tz" in raw:
        tz = raw["tz"]
        if isinstance(tz, bool) or not isinstance(tz, int) or not -840 <= tz <= 840:
            raise PrefsError("Unknown time zone")
        prefs["tz"] = tz
    return prefs


def merged(stored: dict[str, Any] | None) -> dict[str, Any]:
    """Stored settings over the defaults (new kinds start switched on)."""
    stored = stored or {}
    return {
        **DEFAULT_PREFS,
        **{k: v for k, v in stored.items() if k in DEFAULT_PREFS},
        "types": {**DEFAULT_PREFS["types"], **(stored.get("types") or {})},
        "muted_clubs": list(stored.get("muted_clubs") or []),
    }


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def in_quiet(window: dict[str, str] | None, local_minute: int) -> bool:
    if not window:
        return False
    start, end = _minutes(window["from"]), _minutes(window["to"])
    return start <= local_minute < end if start < end else local_minute >= start or local_minute < end


def quiet_now(prefs: dict[str, Any], club_quiet: dict[str, str] | None, now: datetime) -> bool:
    """Quiet by the person's hours or the club's (the stricter wins), in the person's local time."""
    local = (now.hour * 60 + now.minute + int(prefs.get("tz") or 0)) % 1440
    return in_quiet(prefs.get("quiet"), local) or in_quiet(club_quiet, local)


class Notifier:
    def __init__(self, settings: Settings, db: Any, clock: Callable[[], datetime] | None = None) -> None:
        self.db = db
        self.site = settings.site
        self.vapid = webpush.Vapid.from_secret(settings.secret_key, settings.site or "https://localhost")
        self.clock = clock or (lambda: datetime.now(UTC))
        self.sender: Callable[..., None] = webpush.send  # replaced in tests
        self._tasks: set[asyncio.Task[None]] = set()

    async def notify(
        self,
        user_ids: list[int],
        kind: str,
        title: str,
        body: str,
        link: str,
        group: str | None = None,
        club: tuple[int, dict[str, str] | None] | None = None,  # (club id, its quiet hours)
    ) -> list[int]:
        """Notify each person, following their settings. Returns who got it (in the inbox at least)."""
        _label, limit, per_club = KINDS[kind]
        now = self.clock()
        day_ago = now - timedelta(hours=24)
        reached = []
        for uid in dict.fromkeys(user_ids):
            prefs = merged(await self.db.prefs(uid))
            if not prefs["types"].get(kind, True):
                continue
            if club is not None and club[0] in prefs["muted_clubs"]:
                continue
            scope = f"{kind}:{club[0]}" if per_club and club is not None else kind
            if await self.db.count_notifications(uid, scope, day_ago) >= limit:
                continue
            push = not quiet_now(prefs, club[1] if club else None, now)
            push = push and await self.db.count_pushed(uid, day_ago) < PUSH_CAP
            subs = await self.db.push_subs(uid) if push else []
            await self.db.add_notification(
                uid,
                kind,
                scope,
                title[:120],
                body[:240],
                link,
                group,
                pushed=bool(subs),
                group_since=now - timedelta(hours=GROUP_HOURS),
            )
            reached.append(uid)
            for sub in subs:
                self._push(sub, {"title": title[:120], "body": body[:240], "url": link, "tag": group or kind})
        return reached

    def _push(self, sub: Any, payload: dict[str, str]) -> None:
        if len(self._tasks) >= MAX_PENDING:
            log.error("push queue full, dropped one")
            return
        task = asyncio.get_running_loop().create_task(self._deliver(sub, payload))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _deliver(self, sub: Any, payload: dict[str, str]) -> None:
        try:
            await asyncio.to_thread(self.sender, self.vapid, sub.endpoint, sub.p256dh, sub.auth, payload)
        except webpush.Gone:
            await self.db.delete_push_sub(sub.endpoint)
        except Exception as exc:  # noqa: BLE001 - a push failure never reaches the request
            log.error("push failed: %s", type(exc).__name__)

    async def drain(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
