"""Voice and video calls through LiveKit (an SFU: each phone sends its streams once; LiveKit forwards
them, picking the quality each receiver can handle).

The server never touches the media. It only signs short-lived LiveKit access tokens (standard HS256
JWTs, signed here with the stdlib) for people already in the room, and asks LiveKit to remove a
participant when the host removes them from the room.

- The LiveKit room name is an HMAC of the room code: LiveKit never learns the code.
- Identity is the seat id (random); the display name is the player's or watcher's name.
- Players and the audience can talk and show video; a TV screen only subscribes (video only, its
  client plays no audio, so no echo).
- Off unless LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET are all set.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.parse
import urllib.request
from typing import Any

from .config import Settings

log = logging.getLogger("snazzlebop.calls")

TOKEN_TTL = 2 * 3600  # seconds a call token stays valid for joining (a call already joined continues)


def enabled(settings: Settings) -> bool:
    return bool(settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def sign(settings: Settings, claims: dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    parts = (json.dumps(x, separators=(",", ":")).encode() for x in (header, claims))
    body = ".".join(_b64(x) for x in parts)
    mac = hmac.new(settings.livekit_api_secret.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(mac)}"


def room_name(settings: Settings, code: str, created: float) -> str:
    """A stable, unguessable LiveKit room for one Snazzlebop room (never the code itself)."""
    mac = hmac.new(settings.secret_key.encode(), f"call:{code}:{created}".encode(), hashlib.sha256)
    return "snz-" + mac.hexdigest()[:24]


def join_token(settings: Settings, room: str, identity: str, name: str, *, can_publish: bool) -> str:
    now = int(time.time())
    return sign(
        settings,
        {
            "iss": settings.livekit_api_key,
            "sub": identity,
            "name": name,
            "nbf": now - 10,
            "exp": now + TOKEN_TTL,
            "video": {
                "room": room,
                "roomJoin": True,
                "canPublish": can_publish,
                "canSubscribe": True,
                "canPublishData": False,  # game state travels through our server, never the call
            },
        },
    )


def _admin_token(settings: Settings, room: str) -> str:
    now = int(time.time())
    return sign(
        settings,
        {
            "iss": settings.livekit_api_key,
            "nbf": now - 10,
            "exp": now + 60,
            "video": {"room": room, "roomAdmin": True},
        },
    )


def _http_base(settings: Settings) -> str:
    parts = urllib.parse.urlsplit(settings.livekit_url)
    scheme = "https" if parts.scheme in ("wss", "https") else "http"
    return f"{scheme}://{parts.netloc}"


async def remove_participant(settings: Settings, room: str, identity: str) -> None:
    """Best effort: drop someone from the call (the host removed them from the room)."""
    if not enabled(settings):
        return
    req = urllib.request.Request(  # noqa: S310 (the URL is the operator's own LIVEKIT_URL, https in production)
        f"{_http_base(settings)}/twirp/livekit.RoomService/RemoveParticipant",
        data=json.dumps({"room": room, "identity": identity}).encode(),
        headers={
            "Authorization": f"Bearer {_admin_token(settings, room)}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    def call() -> None:
        with urllib.request.urlopen(req, timeout=5):  # noqa: S310  # nosec B310
            pass

    try:
        await asyncio.to_thread(call)
    except Exception:  # not in the call, LiveKit down... nothing to do
        log.info("call: remove participant failed")


def csp_hosts(settings: Settings) -> tuple[str, ...]:
    """What the browser may connect to for calls: the configured LiveKit host (and LiveKit Cloud's
    regional hosts, which it may hand the client)."""
    if not enabled(settings):
        return ()
    host = urllib.parse.urlsplit(settings.livekit_url).netloc
    hosts = [f"wss://{host}", f"https://{host}"]
    if host.endswith(".livekit.cloud"):
        hosts += ["wss://*.livekit.cloud", "https://*.livekit.cloud"]
    return tuple(hosts)
