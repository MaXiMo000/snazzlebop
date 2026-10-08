"""Room snapshots: a whole room (lobby, show, the game in progress) as signed bytes, so live games
survive a restart or a deploy.

A snapshot is a pickle of the Room, with the hub's shared objects (its random source and clock) left
out by reference and plugged back in on load. Pickle runs code on load, so a snapshot is only ever
read after its HMAC (keyed by the server secret) checks out: the bytes must be ones this server wrote.
Live connections and locks are never saved (Room.__getstate__); everyone reconnects on their own.
"""

from __future__ import annotations

import hashlib
import hmac
import io

# Only HMAC-verified snapshots written by this server are ever unpickled.
import pickle  # nosec B403
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .rooms import Room

MAGIC = b"SB1"
MAC_LEN = 32


def _key(secret: str) -> bytes:
    return hmac.new(secret.encode(), b"snazzlebop room snapshot v1", hashlib.sha256).digest()


class _Pickler(pickle.Pickler):
    def __init__(self, file: io.BytesIO, shared: dict[str, Any]) -> None:
        super().__init__(file, protocol=pickle.HIGHEST_PROTOCOL)
        self.shared = {id(obj): name for name, obj in shared.items()}

    def persistent_id(self, obj: Any) -> str | None:
        return self.shared.get(id(obj))


class _Unpickler(pickle.Unpickler):  # fed only bytes whose HMAC was verified
    def __init__(self, file: io.BytesIO, shared: dict[str, Any]) -> None:
        super().__init__(file)
        self.shared = shared

    def persistent_load(self, pid: Any) -> Any:
        if pid not in self.shared:
            raise pickle.UnpicklingError("unknown shared object")
        return self.shared[pid]


def dump_room(room: Room, secret: str, shared: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    _Pickler(buf, shared).dump(room)
    body = buf.getvalue()
    return MAGIC + hmac.new(_key(secret), body, hashlib.sha256).digest() + body


def load_room(blob: bytes, secret: str, shared: dict[str, Any]) -> Room | None:
    """The room in a snapshot, or None if it isn't one this server wrote (or can't be read)."""
    if not blob.startswith(MAGIC) or len(blob) <= len(MAGIC) + MAC_LEN:
        return None
    mac, body = blob[len(MAGIC) : len(MAGIC) + MAC_LEN], blob[len(MAGIC) + MAC_LEN :]
    if not hmac.compare_digest(mac, hmac.new(_key(secret), body, hashlib.sha256).digest()):
        return None
    try:
        # HMAC verified above: these are bytes this server wrote.
        room = _Unpickler(io.BytesIO(body), shared).load()  # nosec B301
    except Exception:  # an old format after an upgrade: that room is simply gone
        return None
    from .rooms import Room

    return room if isinstance(room, Room) else None


def fingerprint(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()[:16]
