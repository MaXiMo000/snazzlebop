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

from . import show as showlib
from .config import Settings
from .games import REGISTRY, Game, GameError, Player, catalog
from .games.base import Deck
from .games.content import THEMES
from .games.jackpot import Jackpot
from .security import sign_token

log = logging.getLogger("snazzlebop.rooms")

ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I/O: avoids lookalikes
ROOM_CODE_RE = re.compile(r"^[A-HJ-NP-Z]{3,8}$")
ALLOWED_MESSAGE_TYPES = {
    *("ping", "start", "act", "skip", "lobby", "leave", "kick", "lock", "title"),
    *("show", "next", "theme", "react", "predict", "trade"),
}
AUDIENCE_MESSAGE_TYPES = {"ping", "react", "predict"}
KICKED = 4001  # WebSocket close code: "the host removed you" (app range 4000-4999)
MAX_TV_PER_ROOM = 2  # big-screen viewers; issuing a third evicts the oldest
MAX_AUDIENCE = 30  # named watchers who can react and predict, beyond the 8 seats
REACTIONS = ("😂", "😱", "👏", "🔥", "🤯", "💀")
REACT_GAP = 0.8  # seconds between reactions from one person (extra taps are ignored, not errors)
ROOM_REACTS_PER_SEC = 6  # and a room-wide ceiling, so a big audience can't turn into a broadcast storm
KEEP_REACTIONS = 12
MARKET_SECONDS = 30.0  # the trading window before each show game


class HubError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class Connection(Protocol):
    async def send_json(self, data: dict[str, Any]) -> None: ...
    async def close(self, code: int = 1000) -> None: ...


def clean_name(raw: object, max_len: int = 16) -> str:
    """Normalise and validate a display name (or room title). Raises HubError if unacceptable."""
    if not isinstance(raw, str):
        raise HubError("bad_name", f"Pick a name between 1 and {max_len} characters")
    if any(unicodedata.category(ch) in ("Cc", "Cf", "Co", "Cs") for ch in raw):
        raise HubError("bad_name", "That name has characters we can't use")
    name = unicodedata.normalize("NFKC", raw)
    name = re.sub(r"\s+", " ", name).strip()
    if not 1 <= len(name) <= max_len:
        raise HubError("bad_name", f"Pick a name between 1 and {max_len} characters")
    for ch in name:
        cat = unicodedata.category(ch)
        # letters, numbers, space, dash/underscore punctuation, apostrophe, dot, and emoji symbols
        if not (cat[0] in "LN" or cat in ("Zs", "Pd", "Pc", "So") or ch in "'."):
            raise HubError("bad_name", "That name has characters we can't use")
    return name


@dataclass
class Watcher:
    """An audience member: named, no seat and no game score, but can react and predict winners."""

    id: str
    name: str
    conn: Connection | None = None
    points: int = 0  # correct winner predictions


@dataclass
class Room:
    code: str
    created: float
    host_id: str = ""
    players: dict[str, Player] = field(default_factory=dict)
    conns: dict[str, Connection] = field(default_factory=dict)
    # TV (spectator) ids -> live connection or None. Not players: no seat, no score, read-only.
    viewers: dict[str, Connection | None] = field(default_factory=dict)
    audience: dict[str, Watcher] = field(default_factory=dict)
    # No-repeat content decks, shared by every game played in this room.
    decks: dict[str, Deck] = field(default_factory=dict)
    phase: str = "lobby"  # lobby | game | results | finale (end of a show)
    title: str = ""  # host-chosen show title
    locked: bool = False  # host stopped new players joining
    theme: str = ""  # show pack (content.THEMES key) or "" for everything
    game: Game | None = None
    show: showlib.Show | None = None
    total_scores: dict[str, int] = field(default_factory=dict)
    highlights: list[dict[str, str]] = field(default_factory=list)  # from the last finished game
    quip: str = ""  # the host's line about the last finished game
    predictions: dict[str, str] = field(default_factory=dict)  # audience id -> predicted winner
    reactions: list[dict[str, Any]] = field(default_factory=list)
    react_seq: int = 0
    react_last: dict[str, float] = field(default_factory=dict)
    react_window: list[float] = field(default_factory=list)
    market_next: str = ""  # the game the open market is waiting for
    market_until: float = 0.0
    market_moves: dict[str, float] = field(default_factory=dict)  # price changes after the last game
    last_active: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def connected_players(self) -> list[Player]:
        return [p for p in self.players.values() if p.connected]

    def names(self) -> dict[str, str]:
        return {p.id: p.name for p in self.players.values()}


class Hub:
    def __init__(
        self,
        settings: Settings,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
        on_game_finished: Callable[[str, dict[str, Any]], None] | None = None,
        on_game_started: Callable[[str, str], None] | None = None,  # (game id, show pack)
        timings: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self.settings = settings
        self.clock = clock
        self.rng = rng or random.SystemRandom()
        self.rooms: dict[str, Room] = {}
        self.on_game_finished = on_game_finished
        self.on_game_started = on_game_started
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
        if room.locked:
            raise HubError("room_locked", "The host has locked this room", 409)
        if room.phase == "game":
            raise HubError("in_progress", "That game has already started", 409)
        if len(room.players) >= self.settings.max_players_per_room:
            raise HubError("room_full", "That room is full", 409)
        self._name_free(room, name)
        player = Player(id=secrets.token_urlsafe(6), name=name, connected=False)
        room.players[player.id] = player
        room.total_scores[player.id] = 0
        room.last_active = self.clock()
        return room, player, self._issue(room, player)

    @staticmethod
    def _name_free(room: Room, name: str) -> None:
        taken = [*(p.name for p in room.players.values()), *(w.name for w in room.audience.values())]
        if any(n.casefold() == name.casefold() for n in taken):
            raise HubError("name_taken", "Someone already has that name", 409)

    def join_audience(self, code: str, name: str) -> tuple[Room, Watcher, str]:
        """A named seat in the crowd: works when the room is full or mid-game, not when it's locked."""
        room = self.get(code.upper() if isinstance(code, str) else code)
        if room is None:
            raise HubError("room_not_found", "No room with that code", 404)
        name = clean_name(name)
        if room.locked:
            raise HubError("room_locked", "The host has locked this room", 409)
        if len(room.audience) >= MAX_AUDIENCE:
            raise HubError("audience_full", "The audience is full", 409)
        self._name_free(room, name)
        watcher = Watcher(id="au:" + secrets.token_urlsafe(6), name=name)
        room.audience[watcher.id] = watcher
        room.last_active = self.clock()
        token = sign_token(self.settings.secret_key, watcher.id, room.code, self.settings.token_ttl_seconds)
        return room, watcher, token

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
        return pid in room.players or pid in room.viewers or pid in room.audience

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
        if pid in room.audience:
            watcher = room.audience[pid]
            previous_conn, watcher.conn = watcher.conn, conn
            room.last_active = self.clock()
            if previous_conn is not None:
                with contextlib.suppress(Exception):
                    await previous_conn.close(1000)
            await self.broadcast(room)  # players see the crowd grow
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
        if pid.startswith("au:"):
            watcher = room.audience.get(pid)
            if watcher is not None and watcher.conn is conn:
                watcher.conn = None
                await self.broadcast(room)
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
        between = room.phase in ("lobby", "results", "finale")
        role = "tv" if pid in room.viewers else "audience" if pid in room.audience else "player"
        return {
            "t": "state",
            "you": pid,
            "tv": role == "tv",
            "role": role,
            "room": {
                "code": room.code,
                "phase": room.phase,
                "host": room.host_id,
                "title": room.title,
                "locked": room.locked,
                "theme": room.theme,
            },
            "themes": THEMES if between else {},
            "show": self._show_view(room),
            "highlights": room.highlights if room.phase == "results" else [],
            "quip": room.quip if room.phase in ("results", "finale") else "",
            "reactions": room.reactions,
            "crowd": self._crowd_view(room, pid),
            "market": self._market_view(room, pid),
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
            "games": catalog() if between else [],
            "game": game_view,
            "stage": room.game.stage if room.game is not None else None,
        }

    @staticmethod
    def _show_view(room: Room) -> dict[str, Any] | None:
        s = room.show
        if s is None:
            return None
        titles = {gid: cls.title for gid, cls in REGISTRY.items()} | {"jackpot": Jackpot.title}
        return {
            "playlist": [{"id": g, "title": titles.get(g, g)} for g in s.playlist],
            "jackpot": s.jackpot,
            "started": s.started,
            "next": s.next_game(),
            "finished": s.finished,
            "games": [{"game": g["game"], "title": g["title"], "scores": g["scores"]} for g in s.games],
            "reel": s.reel if s.finished else [],
            "awards": s.awards if s.finished else [],
            "market": s.market is not None,
        }

    def _market_view(self, room: Room, pid: str) -> dict[str, Any] | None:
        m = room.show.market if room.show else None
        if m is None:
            return None
        titles = {gid: cls.title for gid, cls in REGISTRY.items()}
        finale = room.phase == "finale"
        mine = pid in room.players
        return {
            "open": room.phase == "market",
            "closes_in": max(0.0, room.market_until - self.clock()) if room.phase == "market" else None,
            "next": titles.get(room.market_next, room.market_next) if room.phase == "market" else "",
            "prices": dict(m.prices),
            "history": [dict(h) for h in m.history],
            "moves": dict(room.market_moves),
            "trades": m.trades,
            # Your own book only; everyone's is revealed at the finale.
            "you": {
                "cash": m.cash.get(pid, 0),
                "holdings": dict(m.holdings.get(pid, {})),
                "worth": m.worth(pid),
            }
            if mine
            else None,
            "worth": {p: m.worth(p) for p in m.cash} if finale else {},
            "books": {p: dict(h) for p, h in m.holdings.items()} if finale else {},
            "bonus": {p: m.bonus(p) for p in m.cash} if finale else {},
        }

    @staticmethod
    def _predict_open(room: Room) -> bool:
        g = room.game
        return room.phase == "game" and g is not None and not g.finished and g.round <= 1

    def _crowd_view(self, room: Room, pid: str) -> dict[str, Any]:
        picks: dict[str, int] = {}
        for target in room.predictions.values():
            picks[target] = picks.get(target, 0) + 1
        return {
            "members": [
                {"id": w.id, "name": w.name, "points": w.points, "connected": w.conn is not None}
                for w in room.audience.values()
            ],
            # who can be backed this game: the game's own contestants (not everyone ever seated)
            "contestants": [{"id": p.id, "name": p.name} for p in room.game.players]
            if room.game is not None and room.phase == "game"
            else [],
            "picks": picks,  # how many of the crowd back each player this game (never who)
            "open": self._predict_open(room),
            "you_picked": room.predictions.get(pid),
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
        targets = [
            *room.conns.items(),
            *((v, c) for v, c in room.viewers.items() if c is not None),
            *((w.id, w.conn) for w in room.audience.values() if w.conn is not None),
        ]
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
        if pid in room.audience and kind not in AUDIENCE_MESSAGE_TYPES:
            return await self.send_error(conn, "audience_only", "The audience can react and predict")
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

    def _make_game(self, room: Room, cls: type[Game], **extra: Any) -> Game:
        """Build and start a game for everyone online. Raises (and changes nothing) if it can't start."""
        members = [Player(id=p.id, name=p.name) for p in room.connected_players()]
        game = cls(
            members,
            rng=self.rng,
            clock=self.clock,
            timings=self.timings.get(cls.game_id),
            decks=room.decks,
            theme=room.theme,
            **extra,
        )
        game.start()
        return game

    @staticmethod
    def _options(cls: type[Game], raw: Any) -> dict[str, str]:
        """Only options the game declares, with one of its allowed values."""
        if raw is None:
            return {}
        if not isinstance(raw, dict) or len(raw) > len(cls.OPTIONS):
            raise HubError("bad_options", "Unknown game options")
        for key, value in raw.items():
            if key not in cls.OPTIONS or value not in cls.OPTIONS[key]:
                raise HubError("bad_options", "Unknown game options")
        return dict(raw)

    def _begin(self, room: Room, game: Game) -> None:
        room.game, room.phase = game, "game"
        room.predictions, room.highlights, room.quip = {}, [], ""
        if self.on_game_started and game.game_id in REGISTRY:  # top up content in the background
            try:
                self.on_game_started(game.game_id, room.theme)
            except Exception:
                log.exception("on_game_started failed")

    def _start_next(self, room: Room, s: showlib.Show) -> None:
        """Start the show's next segment, or close the show with the finale."""
        nxt = s.next_game()
        if nxt == "jackpot":
            stakes = {p.id: room.total_scores.get(p.id, 0) for p in room.players.values()}
            self._begin(room, self._make_game(room, Jackpot, stakes=stakes))
            s.jackpot_played = True
        elif nxt is not None:
            game = self._make_game(room, REGISTRY[nxt])  # raises (e.g. too few players) before anything moves
            if s.market is not None:
                self._open_market(room, nxt)
            else:
                self._begin(room, game)
                s.started += 1
        else:
            self._finale(room, s)

    def _open_market(self, room: Room, game_id: str) -> None:
        """Trading window before a show game. The game itself is built when the bell rings."""
        market = room.show.market if room.show else None
        if market is not None:
            for pid in room.players:
                market.seat(pid)
        room.game, room.phase = None, "market"
        room.market_next = game_id
        room.market_until = self.clock() + MARKET_SECONDS
        room.predictions, room.highlights, room.quip = {}, [], ""

    def _close_market(self, room: Room) -> None:
        s = room.show
        if s is None or room.phase != "market":
            return
        try:
            game = self._make_game(room, REGISTRY[room.market_next])
        except (GameError, HubError):
            # Someone left during trading and the game can't run: skip it and move on.
            s.started += 1
            room.phase = "results"
            self._start_next(room, s)
            return
        self._begin(room, game)
        s.started += 1

    def _finale(self, room: Room, s: showlib.Show) -> None:
        s.finished = True
        if s.market is not None:  # net worth becomes show points: $10 = 1 point, either way
            for pid in room.players:
                s.market.seat(pid)
                room.total_scores[pid] = room.total_scores.get(pid, 0) + s.market.bonus(pid)
        totals = {pid: room.total_scores.get(pid, 0) for pid in room.players}
        names = room.names()
        s.awards = showlib.awards(s, totals, names)
        if s.market is not None and room.players:
            tycoon = max(room.players, key=s.market.worth)
            worth = s.market.worth(tycoon)
            if worth > showlib.START_CASH:
                s.awards.append(
                    {
                        "icon": "📈",
                        "title": "Market tycoon",
                        "text": f"{names.get(tycoon, '?')} ended worth ${worth:,}",
                    }
                )
        s.quip = room.quip = showlib.quip(
            totals, names, room.title or "the show", room.decks, self.rng, "show"
        )
        room.game, room.phase = None, "finale"

    def _apply(self, room: Room, pid: str, kind: str, msg: dict[str, Any]) -> bool:
        is_host = pid == room.host_id
        if kind == "react":
            return self._react(room, pid, msg)
        if kind == "predict":
            if pid not in room.audience:
                raise HubError("audience_only", "Only the audience predicts")
            if not self._predict_open(room) or room.game is None:
                raise HubError("predict_closed", "Predictions are closed for this game")
            target = msg.get("target")
            if not isinstance(target, str) or target not in room.game.player_ids:
                raise HubError("bad_target", "Pick a contestant")
            room.predictions[pid] = target
            return True
        if kind == "start":
            if not is_host:
                raise HubError("not_host", "Only the host can start a game", 403)
            if room.phase == "game":
                raise HubError("in_progress", "A game is already running", 409)
            cls = REGISTRY.get(msg.get("game")) if isinstance(msg.get("game"), str) else None
            if cls is None:
                raise HubError("bad_game", "Unknown game")
            self._begin(room, self._make_game(room, cls, options=self._options(cls, msg.get("options"))))
            room.show = None  # a one-off game outside any show
            return True
        if kind == "show":
            if not is_host:
                raise HubError("not_host", "Only the host can start a show", 403)
            if room.phase == "game":
                raise HubError("in_progress", "A game is already running", 409)
            raw = msg.get("games")
            if (
                not isinstance(raw, list)
                or not showlib.MIN_GAMES <= len(raw) <= showlib.MAX_GAMES
                or any(not isinstance(g, str) or g not in REGISTRY for g in raw)
                or len(set(raw)) != len(raw)
            ):
                raise HubError("bad_show", f"Pick {showlib.MIN_GAMES}-{showlib.MAX_GAMES} different games")
            jackpot = msg.get("jackpot", True)
            market = msg.get("market", False)
            if not isinstance(jackpot, bool) or not isinstance(market, bool):
                raise HubError("bad_message", "Unknown message")
            game = self._make_game(room, REGISTRY[raw[0]])  # raises before anything changes
            room.total_scores = {p: 0 for p in room.players}  # a new show, a fresh scoreboard
            if market:
                room.show = showlib.Show(playlist=list(raw), jackpot=jackpot, market=showlib.Market())
                self._open_market(room, raw[0])
            else:
                room.show = showlib.Show(playlist=list(raw), jackpot=jackpot, started=1)
                self._begin(room, game)
            return True
        if kind == "trade":
            market = room.show.market if room.show else None
            if pid not in room.players or market is None or room.phase != "market":
                raise HubError("market_closed", "The market is closed")
            target, qty = msg.get("target"), msg.get("qty")
            if not isinstance(target, str) or target not in room.players:
                raise HubError("bad_trade", "Pick a player to trade")
            if isinstance(qty, bool) or not isinstance(qty, int):
                raise HubError("bad_trade", "Trade a whole number of shares")
            market.seat(pid)
            market.seat(target)
            try:
                market.trade(pid, target, qty)
            except ValueError as exc:
                raise HubError("bad_trade", str(exc)) from None
            return True
        if kind == "next":
            if not is_host:
                raise HubError("not_host", "Only the host can do that", 403)
            s = room.show
            if s is None or s.finished or room.phase != "results":
                raise HubError("no_show", "No show segment to start")
            if msg.get("skip") is True and s.next_game() not in (None, "jackpot"):
                s.started += 1  # e.g. not enough players online for that game
            self._start_next(room, s)
            return True
        if kind == "theme":
            if not is_host:
                raise HubError("not_host", "Only the host can do that", 403)
            theme = msg.get("theme")
            if not isinstance(theme, str) or (theme and theme not in THEMES):
                raise HubError("bad_theme", "Unknown show pack")
            room.theme = theme
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
            if room.phase == "market":  # the host rings the closing bell early
                self._close_market(room)
                return True
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
            room.game, room.phase, room.show = None, "lobby", None
            room.highlights, room.quip, room.predictions = [], "", {}
            return True
        if kind in ("kick", "lock", "title"):
            if not is_host:
                raise HubError("not_host", "Only the host can do that", 403)
            return self._host_tool(room, pid, kind, msg)
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

    def _host_tool(self, room: Room, pid: str, kind: str, msg: dict[str, Any]) -> bool:
        if kind == "title":
            raw = msg.get("title")
            room.title = "" if raw == "" else clean_name(raw, max_len=32)
            return True
        if kind == "lock":
            if not isinstance(msg.get("locked"), bool):
                raise HubError("bad_message", "Unknown message")
            room.locked = msg["locked"]
            return True
        target = msg.get("target")
        if isinstance(target, str) and target in room.audience:  # the crowd can go at any time
            watcher = room.audience.pop(target)
            room.predictions.pop(target, None)
            if watcher.conn is not None:
                asyncio.get_running_loop().create_task(watcher.conn.close(KICKED))
            return True
        if not isinstance(target, str) or target not in room.players or target == pid:
            raise HubError("bad_target", "Pick another player")
        if room.phase == "game":
            raise HubError("in_progress", "Remove players between games")
        del room.players[target]
        room.total_scores.pop(target, None)
        conn = room.conns.pop(target, None)
        if conn is not None:
            asyncio.get_running_loop().create_task(conn.close(KICKED))
        return True

    def _react(self, room: Room, pid: str, msg: dict[str, Any]) -> bool:
        emoji = msg.get("e")
        if emoji not in REACTIONS:
            raise HubError("bad_reaction", "Unknown reaction")
        now = self.clock()
        if now - room.react_last.get(pid, -1e9) < REACT_GAP:
            return False  # tapping faster than that just doesn't count
        room.react_window = [t for t in room.react_window if now - t < 1.0]
        if len(room.react_window) >= ROOM_REACTS_PER_SEC:
            return False
        room.react_last[pid] = now
        room.react_window.append(now)
        who = room.players.get(pid) or room.audience.get(pid)
        room.react_seq += 1
        room.reactions = [
            *room.reactions[-(KEEP_REACTIONS - 1) :],
            {"id": room.react_seq, "e": emoji, "by": who.name if who else "?"},
        ]
        return True

    def _maybe_finish(self, room: Room) -> None:
        game = room.game
        if game is None or not game.finished or room.phase != "game":
            return
        scores = game.scores()
        for pid, pts in scores.items():
            room.total_scores[pid] = room.total_scores.get(pid, 0) + pts
        room.phase = "results"
        names = room.names()
        try:
            room.highlights = game.highlights()
        except Exception:  # a highlight bug must never cost anyone their result
            log.exception("highlights failed")
            room.highlights = []
        final = "jackpot" if game.game_id == "jackpot" else None
        room.quip = showlib.quip(scores, names, game.title, room.decks, self.rng, final)
        if scores:  # the crowd's predictions: everyone who backed a winner gets a point
            top = max(scores.values())
            for au, target in room.predictions.items():
                watcher = room.audience.get(au)
                if watcher is not None and scores.get(target) == top:
                    watcher.points += 1
        if room.show is not None and room.show.market is not None and game.game_id != "jackpot":
            for pid in scores:
                room.show.market.seat(pid)
            room.market_moves = room.show.market.reprice(scores)
        if room.show is not None:
            room.show.games.append({"game": game.game_id, "title": game.title, "scores": dict(scores)})
            room.show.reel.extend({**h, "game": game.title} for h in room.highlights)
        if self.on_game_finished:
            try:
                self.on_game_finished(game.game_id, game.summary())
            except Exception:
                log.exception("failed to record game result")

    # -- timers -------------------------------------------------------------
    async def tick(self) -> None:
        for room in list(self.rooms.values()):
            if room.phase == "market" and self.clock() >= room.market_until:
                async with room.lock:
                    self._close_market(room)
                await self.broadcast(room)
                continue
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
