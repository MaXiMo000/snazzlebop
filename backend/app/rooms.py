"""Rooms, players and the message router. Framework-free: connections are a tiny protocol."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import re
import secrets
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import Settings
from .games import REGISTRY, Game, GameError, Player, catalog
from .games.base import Deck
from .security import sign_token

log = logging.getLogger("snazzlebop.rooms")

ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I/O: avoids lookalikes
ROOM_CODE_RE = re.compile(r"^[A-HJ-NP-Z]{3,8}$")
ALLOWED_MESSAGE_TYPES = {"ping", "start", "act", "skip", "lobby", "leave"}
MAX_TV_PER_ROOM = 2  # big-screen viewers; issuing a third evicts the oldest


class HubError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class Connection(Protocol):
    async def send_json(self, data: dict[str, Any]) -> None: ...
    async def close(self, code: int = 1000) -> None: ...


def clean_name(raw: object) -> str:
    """Normalise and validate a display name. Raises HubError if unacceptable."""
    if not isinstance(raw, str):
        raise HubError("bad_name", "Pick a name between 1 and 16 characters")
    if any(unicodedata.category(ch) in ("Cc", "Cf", "Co", "Cs") for ch in raw):
        raise HubError("bad_name", "That name has characters we can't use")
    name = unicodedata.normalize("NFKC", raw)
    name = re.sub(r"\s+", " ", name).strip()
    if not 1 <= len(name) <= 16:
        raise HubError("bad_name", "Pick a name between 1 and 16 characters")
    for ch in name:
        cat = unicodedata.category(ch)
        # letters, numbers, space, dash/underscore punctuation, apostrophe, dot, and emoji symbols
        if not (cat[0] in "LN" or cat in ("Zs", "Pd", "Pc", "So") or ch in "'."):
            raise HubError("bad_name", "That name has characters we can't use")
    return name


@dataclass
class Room:
    code: str
    created: float
    host_id: str = ""
    players: dict[str, Player] = field(default_factory=dict)
    conns: dict[str, Connection] = field(default_factory=dict)
    # TV (spectator) ids -> live connection or None. Not players: no seat, no score, read-only.
    viewers: dict[str, Connection | None] = field(default_factory=dict)
    # No-repeat content decks, shared by every game played in this room.
    decks: dict[str, Deck] = field(default_factory=dict)
    phase: str = "lobby"  # lobby | game | results
    game: Game | None = None
    total_scores: dict[str, int] = field(default_factory=dict)
    last_active: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def connected_players(self) -> list[Player]:
        return [p for p in self.players.values() if p.connected]


class Hub:
    def __init__(
        self,
        settings: Settings,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
        on_game_finished: Callable[[str, dict[str, Any]], None] | None = None,
        timings: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self.settings = settings
        self.clock = clock
        self.rng = rng or random.SystemRandom()
        self.rooms: dict[str, Room] = {}
        self.on_game_finished = on_game_finished
        self.timings = timings or {}
        self.send_timeout = 5.0  # a socket that can't take a frame this long is dropped
        self._mail: dict[Connection, dict[str, Any]] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    # -- rooms --------------------------------------------------------------
    def _new_code(self) -> str:
        for _ in range(50):
            code = "".join(secrets.choice(ROOM_ALPHABET) for _ in range(self.settings.room_code_length))
            if code not in self.rooms:
                return code
        raise HubError("busy", "Try again in a moment", 503)

    def _issue(self, room: Room, player: Player) -> str:
        return sign_token(self.settings.secret_key, player.id, room.code, self.settings.token_ttl_seconds)

    def create_room(self, name: str) -> tuple[Room, Player, str]:
        self.cleanup()
        if len(self.rooms) >= self.settings.max_rooms:
            raise HubError("busy", "The party house is full right now. Try again soon.", 503)
        name = clean_name(name)
        room = Room(code=self._new_code(), created=self.clock(), last_active=self.clock())
        player = Player(id=secrets.token_urlsafe(6), name=name, connected=False)
        room.players[player.id] = player
        room.host_id = player.id
        room.total_scores[player.id] = 0
        self.rooms[room.code] = room
        return room, player, self._issue(room, player)

    def get(self, code: str) -> Room | None:
        if not isinstance(code, str) or not ROOM_CODE_RE.match(code):
            return None
        return self.rooms.get(code)

    def join_room(self, code: str, name: str) -> tuple[Room, Player, str]:
        room = self.get(code.upper() if isinstance(code, str) else code)
        if room is None:
            raise HubError("room_not_found", "No room with that code", 404)
        name = clean_name(name)
        if room.phase == "game":
            raise HubError("in_progress", "That game has already started", 409)
        if len(room.players) >= self.settings.max_players_per_room:
            raise HubError("room_full", "That room is full", 409)
        if any(p.name.casefold() == name.casefold() for p in room.players.values()):
            raise HubError("name_taken", "Someone already has that name", 409)
        player = Player(id=secrets.token_urlsafe(6), name=name, connected=False)
        room.players[player.id] = player
        room.total_scores[player.id] = 0
        room.last_active = self.clock()
        return room, player, self._issue(room, player)

    def issue_tv(self, code: str) -> tuple[Room, str]:
        """A read-only big-screen seat. Same trust as joining: anyone holding the room code."""
        room = self.get(code.upper() if isinstance(code, str) else code)
        if room is None:
            raise HubError("room_not_found", "No room with that code", 404)
        vid = "tv:" + secrets.token_urlsafe(6)
        room.viewers[vid] = None
        while len(room.viewers) > MAX_TV_PER_ROOM:
            oldest = next(iter(room.viewers))
            conn = room.viewers.pop(oldest)
            if conn is not None:
                asyncio.get_running_loop().create_task(conn.close(1008))
        token = sign_token(self.settings.secret_key, vid, room.code, self.settings.token_ttl_seconds)
        return room, token

    def is_member(self, room: Room, pid: str) -> bool:
        return pid in room.players or pid in room.viewers

    def cleanup(self) -> None:
        now = self.clock()
        for code, room in list(self.rooms.items()):
            idle = not room.conns and now - room.last_active > self.settings.room_idle_seconds
            old = now - room.created > self.settings.room_max_age_seconds
            if idle or old:
                del self.rooms[code]

    # -- connections --------------------------------------------------------
    async def connect(self, room: Room, pid: str, conn: Connection) -> None:
        if pid in room.viewers:
            previous = room.viewers[pid]
            room.viewers[pid] = conn
            if previous is not None:
                with contextlib.suppress(Exception):
                    await previous.close(1000)
            task = self._post(room, pid, conn, self.view_for(room, pid))  # only the screen needs a frame
            if task is not None:
                await asyncio.wait([task], timeout=0.25)
            return
        async with room.lock:
            previous = room.conns.get(pid)
            room.conns[pid] = conn
            room.players[pid].connected = True
            room.last_active = self.clock()
        if previous is not None:
            with contextlib.suppress(Exception):  # already gone
                await previous.close(1000)
        await self.broadcast(room)

    async def disconnect(self, room: Room, pid: str, conn: Connection) -> None:
        if pid in room.viewers or pid.startswith("tv:"):
            if room.viewers.get(pid) is conn:
                room.viewers[pid] = None
            return
        async with room.lock:
            if room.conns.get(pid) is not conn:
                return  # superseded by a newer connection
            room.conns.pop(pid, None)
            player = room.players.get(pid)
            if player:
                player.connected = False
            if room.host_id == pid:
                heir = next((p.id for p in room.players.values() if p.connected), None)
                if heir:
                    room.host_id = heir
            room.last_active = self.clock()
        await self.broadcast(room)

    # -- views --------------------------------------------------------------
    def view_for(self, room: Room, pid: str) -> dict[str, Any]:
        game_view = None
        if room.game is not None and room.phase in ("game", "results"):
            game_view = room.game.view_for(pid)
        return {
            "t": "state",
            "you": pid,
            "tv": pid in room.viewers,
            "room": {"code": room.code, "phase": room.phase, "host": room.host_id},
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "connected": p.connected,
                    "host": p.id == room.host_id,
                    "total": room.total_scores.get(p.id, 0),
                }
                for p in room.players.values()
            ],
            "games": catalog() if room.phase in ("lobby", "results") else [],
            "game": game_view,
            "stage": room.game.stage if room.game is not None else None,
        }

    # -- outbound: one mailbox per connection, latest state wins ---------------------------------
    # Every frame is a full snapshot, so a connection only ever needs the newest one. If a send is
    # already in flight (slow or non-reading client), the next state just replaces the pending one
    # and the broadcaster moves on: a stuck socket can never stall the players who are acting.
    def _post(
        self, room: Room, pid: str, conn: Connection, data: dict[str, Any]
    ) -> asyncio.Task[None] | None:
        box = self._mail.get(conn)
        if box is not None:
            box["pending"] = data
            return None
        self._mail[conn] = {"pending": data}
        task = asyncio.get_running_loop().create_task(self._drain(room, pid, conn))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _drain(self, room: Room, pid: str, conn: Connection) -> None:
        box = self._mail[conn]
        try:
            while box["pending"] is not None:
                data, box["pending"] = box["pending"], None
                await asyncio.wait_for(conn.send_json(data), timeout=self.send_timeout)
        except Exception:
            # Slow or dead client: drop it (once) rather than queue frames for it.
            self._mail.pop(conn, None)
            log.info("dropping unresponsive connection")
            with contextlib.suppress(Exception):
                await conn.close(1011)
            await self.disconnect(room, pid, conn)
            return
        self._mail.pop(conn, None)

    async def broadcast(self, room: Room) -> None:
        targets = [*room.conns.items(), *((v, c) for v, c in room.viewers.items() if c is not None)]
        tasks = [
            task
            for pid, conn in targets
            if (task := self._post(room, pid, conn, self.view_for(room, pid))) is not None
        ]
        if tasks:
            # Healthy sockets finish almost at once; anything slower keeps going in the background.
            await asyncio.wait(tasks, timeout=0.25)
        else:
            # Every recipient already has a send in flight: yield so those drains can run even if
            # our caller never awaits anything else.
            await asyncio.sleep(0)

    async def send_error(self, conn: Connection, code: str, message: str) -> None:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(conn.send_json({"t": "error", "code": code, "message": message}), 5)

    # -- message routing ----------------------------------------------------
    async def handle_message(self, room: Room, pid: str, conn: Connection, msg: Any) -> None:
        if not isinstance(msg, dict) or msg.get("t") not in ALLOWED_MESSAGE_TYPES:
            return await self.send_error(conn, "bad_message", "Unknown message")
        kind = msg["t"]
        if pid in room.viewers:
            # TV screens only watch: no actions, and their keep-alive pings don't keep a room alive.
            if kind != "ping":
                await self.send_error(conn, "read_only", "TV mode is read-only")
            return
        room.last_active = self.clock()
        if kind == "ping":
            return
        try:
            async with room.lock:
                changed = self._apply(room, pid, kind, msg)
            if changed:
                await self.broadcast(room)
        except (GameError, HubError) as exc:
            await self.send_error(conn, exc.code, exc.message)

    def _apply(self, room: Room, pid: str, kind: str, msg: dict[str, Any]) -> bool:
        is_host = pid == room.host_id
        if kind == "start":
            if not is_host:
                raise HubError("not_host", "Only the host can start a game", 403)
            if room.phase == "game":
                raise HubError("in_progress", "A game is already running", 409)
            cls = REGISTRY.get(msg.get("game")) if isinstance(msg.get("game"), str) else None
            if cls is None:
                raise HubError("bad_game", "Unknown game")
            members = [Player(id=p.id, name=p.name) for p in room.connected_players()]
            game = cls(
                members,
                rng=self.rng,
                clock=self.clock,
                timings=self.timings.get(cls.game_id),
                decks=room.decks,
            )
            game.start()
            room.game, room.phase = game, "game"
            return True
        if kind == "act":
            if room.game is None or room.phase != "game":
                raise HubError("no_game", "No game is running")
            action = {k: v for k, v in msg.items() if k != "t"}
            room.game.handle(pid, action)
            self._maybe_finish(room)
            return True
        if kind == "skip":
            if not is_host:
                raise HubError("not_host", "Only the host can skip", 403)
            if room.game is None or room.phase != "game":
                raise HubError("no_game", "No game is running")
            seen = msg.get("stage")
            if seen is not None:
                if not isinstance(seen, str) or len(seen) > 32:
                    raise HubError("bad_message", "Unknown message")
                if seen != room.game.stage:
                    return False  # the wait the host meant to skip already ended on its own
            room.game.advance()
            self._maybe_finish(room)
            return True
        if kind == "lobby":
            if not is_host:
                raise HubError("not_host", "Only the host can do that", 403)
            room.game, room.phase = None, "lobby"
            return True
        if kind == "leave":
            player = room.players.get(pid)
            if player and room.phase == "lobby" and pid != room.host_id:
                del room.players[pid]
                room.total_scores.pop(pid, None)
                conn = room.conns.pop(pid, None)
                if conn is not None:
                    asyncio.get_running_loop().create_task(conn.close(1000))
            return True
        return False

    def _maybe_finish(self, room: Room) -> None:
        game = room.game
        if game is None or not game.finished or room.phase != "game":
            return
        for pid, pts in game.scores().items():
            room.total_scores[pid] = room.total_scores.get(pid, 0) + pts
        room.phase = "results"
        if self.on_game_finished:
            try:
                self.on_game_finished(game.game_id, game.summary())
            except Exception:
                log.exception("failed to record game result")

    # -- timers -------------------------------------------------------------
    async def tick(self) -> None:
        for room in list(self.rooms.values()):
            game = room.game
            if game is None or room.phase != "game":
                continue
            async with room.lock:
                before = game.version
                game.tick()
                self._maybe_finish(room)
                changed = game.version != before
            if changed:
                await self.broadcast(room)

    async def run_ticker(self, interval: float = 0.5) -> None:
        while True:
            try:
                await self.tick()
                self.cleanup()
            except Exception:
                log.exception("ticker error")
            await asyncio.sleep(interval)
