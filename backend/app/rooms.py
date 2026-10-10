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
from collections.abc import Awaitable, Callable
from dataclasses import MISSING, dataclass, field, fields
from typing import Any, Protocol

from . import calls, persist, prank
from . import coins as coinlib
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
    *("show", "next", "theme", "react", "predict", "trade", "card", "mvp", "rematch", "ready", "boost"),
    *("shuffle", "ink", "inksync", "chat", "call", "avatar", "hush", "crown", "forfeit", "wheel"),
}
TEAM_MIN_PLAYERS = 4  # two teams of at least two
AUDIENCE_MESSAGE_TYPES = {"ping", "react", "predict", "trade", "mvp", "inksync", "chat", "call", "avatar"}
# The loser's wheel: the host's group writes its own forfeits; these fill the wheel until they have.
DEFAULT_FORFEITS = (
    "Sing the chorus of a song the room picks",
    "Talk in a robot voice until the next game ends",
    "Change your name to Potato for the next game",
    "Do your best impression of the winner",
    "Say something nice about everyone in the room",
    "Speak only in questions for two minutes",
    "Show the last photo on your phone",
    "Dance for ten seconds, no music",
    "Give the winner a royal title and use it all night",
    "Tell your most embarrassing story in thirty seconds",
)
MAX_FORFEITS, FORFEIT_MAX, WHEEL_SLOTS, WHEEL_GAP = 20, 80, 8, 6.0
AVATAR_FACES, AVATAR_TONES = 24, 8  # a picked face and colour: indexes into the client's fixed lists
CALL_GAP = 5.0  # seconds between call passes for one person
# Chat: plain text, short, rate-limited per person and per room; only the latest messages are kept (in
# memory and the room's snapshot, gone with the room). Logs never contain chat text.
CHAT_MAX = 200
CHAT_KEEP = 80
CHAT_SHOWN = 40
CHAT_GAP = 0.9  # seconds between messages from one person
CHAT_ROOM_BURST = (12, 5.0)  # at most 12 messages per 5 seconds room-wide
INK_BACKLOG = 300  # queued pen strokes per screen; past this it just gets told to redraw from scratch
KICKED = 4001  # WebSocket close code: "the host removed you" (app range 4000-4999)
MAX_TV_PER_ROOM = 2  # big-screen viewers; issuing a third evicts the oldest
MAX_AUDIENCE = 30  # named watchers who can react and predict, beyond the 8 seats
REACTIONS = ("😂", "😱", "👏", "🔥", "🤯", "💀")
REACT_GAP = 0.8  # seconds between reactions from one person (extra taps are ignored, not errors)
ROOM_REACTS_PER_SEC = 6  # and a room-wide ceiling, so a big audience can't turn into a broadcast storm
KEEP_REACTIONS = 12
MARKET_SECONDS = 30.0  # the trading window before each show game
FAN_BONUS = 50  # the audience's MVP of a show game
INTRO_SECONDS = 45.0  # "how to play" before every game; it starts sooner once everyone taps Ready


class HubError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class Connection(Protocol):
    async def send_json(self, data: dict[str, Any]) -> None: ...
    async def close(self, code: int = 1000) -> None: ...


class SnapshotStore(Protocol):
    """Where room snapshots live (db.Database). Every call fails soft: rooms work without it."""

    ready: bool

    async def save_snapshot(self, code: str, data: bytes) -> None: ...
    async def load_snapshot(self, code: str) -> bytes | None: ...
    async def delete_snapshots(self, codes: list[str]) -> None: ...


def clean_chat(raw: Any) -> str:
    """A chat message: one line of plain text. Emoji are fine (including joined ones); control and
    invisible formatting characters (bidi overrides, zero-width tricks) are not."""
    if not isinstance(raw, str):
        raise HubError("bad_message", "Type a message")
    text = " ".join(raw.split())
    if not text:
        raise HubError("bad_message", "Type a message")
    if len(text) > CHAT_MAX:
        raise HubError("too_long", f"Messages are up to {CHAT_MAX} characters")
    for ch in text:
        cat = unicodedata.category(ch)
        if cat[0] == "C" and ch != "\u200d":  # keep the zero-width joiner that builds family and flag emoji
            raise HubError("bad_message", "That message has characters we can't show")
    return text


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
    chat: list[dict[str, Any]] = field(default_factory=list)  # {"id", "by", "name", "text", "team"}
    chat_seq: int = 0
    chat_last: dict[str, float] = field(default_factory=dict)
    chat_window: list[float] = field(default_factory=list)
    call_last: dict[str, float] = field(default_factory=dict)
    call_hush: int = 0  # goes up when the host mutes everyone; each screen mutes its own microphone
    faces: dict[str, list[int]] = field(default_factory=dict)  # pid -> [face, tone], picked by that person
    entrance: dict[str, Any] = field(default_factory=dict)  # the latest walk-on: {id, pid, name}
    belt: str = ""  # the display name of the reigning champion (kept with the host's account)
    forfeits: list[str] = field(default_factory=list)  # the group's own dares for the loser's wheel
    wheel: dict[str, Any] = field(default_factory=dict)  # the last spin: {n, pid, name, options, pick}
    market_next: str = ""  # the game the open market is waiting for
    market_until: float = 0.0
    market_moves: dict[str, float] = field(default_factory=dict)  # price changes after the last game
    market_dividends: dict[str, int] = field(default_factory=dict)  # cash paid after the last game
    insider: str = ""  # who got this trading window's tip
    tip: str = ""
    rivals: list[tuple[str, str]] = field(default_factory=list)  # this show game's pairings
    rival_news: list[dict[str, Any]] = field(default_factory=list)  # who beat whom, last game
    card_news: list[dict[str, Any]] = field(default_factory=list)  # cards revealed, last game
    mvp_votes: dict[str, str] = field(default_factory=dict)  # audience id -> MVP of the last game
    season_no: int = 0  # shows finished in this room
    season: dict[str, dict[str, int]] = field(default_factory=dict)  # pid -> {"wins", "points"}
    last_show: dict[str, Any] = field(default_factory=dict)  # for the rematch button
    # The "how to play" screen before a game: {"game", "options", "slot"}; the game is built at the end.
    intro: dict[str, Any] = field(default_factory=dict)
    intro_until: float = 0.0
    ready: set[str] = field(default_factory=set)  # who tapped Ready (intro, or a skippable results screen)
    ready_stage: str = ""  # the game stage those votes are for
    last_standings: list[dict[str, Any]] = field(default_factory=list)  # the last finale, kept for the lobby
    # The prank: how many scares each matching person has been sent (only they ever see their count).
    scares: dict[str, int] = field(default_factory=dict)
    last_active: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Accounts (private: never in any view): seat -> account id, for coins, stats and power-ups.
    accounts: dict[str, int] = field(default_factory=dict)
    game_no: int = 0  # games started in this room
    boosts: list[dict[str, Any]] = field(default_factory=list)  # power-ups bought with coins, as plays
    boost_peeks: dict[str, str] = field(default_factory=dict)  # what a bought Peek showed (private)
    coin_news: dict[str, dict[str, int]] = field(default_factory=dict)  # last game: pid -> place, coins
    teams: dict[str, int] = field(default_factory=dict)  # this game's teams (player -> 0/1); {} = no teams
    team_news: dict[str, Any] = field(default_factory=dict)  # last game: team totals and the winner
    # Snapshots: this copy came from the database and nothing has changed here since (so a newer
    # snapshot, written by the server that's shutting down during a deploy, may replace it).
    restored: bool = False
    touched: bool = False
    snapshot: str = ""  # fingerprint of the snapshot this copy was loaded from

    # Saved without anything live: connections and locks belong to this process only.
    def __getstate__(self) -> dict[str, Any]:
        state = self.__dict__.copy()
        state.pop("lock", None)
        state["conns"] = {}
        state["viewers"] = dict.fromkeys(self.viewers)
        state["audience"] = {k: Watcher(w.id, w.name, None, w.points) for k, w in self.audience.items()}
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)
        for f in fields(self):  # a snapshot from before a field existed: start it at its default
            if f.name not in state and f.default_factory is not MISSING:
                setattr(self, f.name, f.default_factory())
        self.lock = asyncio.Lock()
        for p in self.players.values():
            p.connected = False

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
        intro_seconds: float = INTRO_SECONDS,  # 0 = games start straight away (used by unit tests)
        store: SnapshotStore | None = None,  # saves rooms so they survive a restart (None: memory only)
        # Accounts: pay coins for a finished game ({account: coins} paid), spend / refund a power-up.
        on_results: Callable[[list[dict[str, Any]]], Awaitable[dict[int, int]]] | None = None,
        spend_powerup: Callable[[int, str], Awaitable[bool]] | None = None,
        refund_powerup: Callable[[int, str], Awaitable[None]] | None = None,
        # (host's account, belt holder's name, forfeits): remembered for that host's next rooms
        save_circle: Callable[[int, str, list[str]], Awaitable[None]] | None = None,
    ) -> None:
        self.settings = settings
        self.clock = clock
        self.rng = rng or random.SystemRandom()
        self.rooms: dict[str, Room] = {}
        self.on_game_finished = on_game_finished
        self.on_game_started = on_game_started
        self.timings = timings or {}
        self.intro_seconds = intro_seconds
        self.prank_targets = prank.targets(settings.jumpscare_names) if settings.jumpscare else ()
        self.send_timeout = 5.0  # a socket that can't take a frame this long is dropped
        self._mail: dict[Connection, dict[str, Any]] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self.store = store
        self.on_results = on_results
        self.spend_powerup = spend_powerup
        self.refund_powerup = refund_powerup
        self.save_circle = save_circle
        self._saving: dict[str, bool] = {}  # room code -> another save is due once this one lands

    # -- snapshots: rooms survive a restart ----------------------------------------------------------
    def _shared(self) -> dict[str, Any]:
        return {"rng": self.rng, "clock": self.clock}

    def _persist(self, room: Room) -> None:
        """Save this room soon. Saves never overlap per room; the newest state always lands last."""
        room.touched = True
        if self.store is None or not self.store.ready:
            return
        if room.code in self._saving:
            self._saving[room.code] = True
            return
        try:
            task = asyncio.get_running_loop().create_task(self._save(room))
        except RuntimeError:  # no event loop (a sync caller in tests): nothing to save with
            return
        self._saving[room.code] = False
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _save(self, room: Room) -> None:
        try:
            while True:
                self._saving[room.code] = False
                if self.rooms.get(room.code) is not room or self.store is None:
                    return
                try:
                    blob = persist.dump_room(room, self.settings.secret_key, self._shared())
                except Exception:
                    log.exception("could not snapshot a room")
                    return
                await self.store.save_snapshot(room.code, blob)
                if not self._saving.get(room.code):
                    return
        finally:
            self._saving.pop(room.code, None)

    async def flush(self) -> None:
        """Save every room now (shutdown: the next server picks them up)."""
        if self.store is None or not self.store.ready:
            return
        for room in list(self.rooms.values()):
            try:
                blob = persist.dump_room(room, self.settings.secret_key, self._shared())
            except Exception:
                log.exception("could not snapshot a room")
                continue
            await self.store.save_snapshot(room.code, blob)

    async def fetch(self, code: str) -> Room | None:
        """The room with this code: in memory, or restored from its snapshot after a restart. A copy
        restored here that nobody has touched yet is refreshed if a newer snapshot has landed (during a
        deploy the old server keeps saving until it shuts down)."""
        if not isinstance(code, str) or not ROOM_CODE_RE.match(code):
            return None
        room = self.rooms.get(code)
        if room is not None and not (room.restored and not room.touched):
            return room
        if self.store is None or not self.store.ready:
            return room
        blob = await self.store.load_snapshot(code)
        if blob is None:
            return room
        if room is not None and persist.fingerprint(blob) == room.snapshot:
            return room
        loaded = persist.load_room(blob, self.settings.secret_key, self._shared())
        if loaded is None or self.clock() - loaded.created > self.settings.room_max_age_seconds:
            return room
        if self.rooms.get(code) is not room:  # someone else restored it while we waited
            return self.rooms.get(code)
        loaded.restored, loaded.touched, loaded.snapshot = True, False, persist.fingerprint(blob)
        loaded.last_active = self.clock()
        self.rooms[code] = loaded
        log.info("room restored from its snapshot")
        return loaded

    # -- rooms --------------------------------------------------------------
    def _new_code(self) -> str:
        for _ in range(50):
            code = "".join(secrets.choice(ROOM_ALPHABET) for _ in range(self.settings.room_code_length))
            if code not in self.rooms:
                return code
        raise HubError("busy", "Try again in a moment", 503)

    def _issue(self, room: Room, player: Player) -> str:
        return sign_token(self.settings.secret_key, player.id, room.code, self.settings.token_ttl_seconds)

    def create_room(
        self, name: str, user_id: int | None = None, circle: dict[str, Any] | None = None
    ) -> tuple[Room, Player, str]:
        self.cleanup()
        if len(self.rooms) >= self.settings.max_rooms:
            raise HubError("busy", "The party house is full right now. Try again soon.", 503)
        name = clean_name(name)
        room = Room(code=self._new_code(), created=self.clock(), last_active=self.clock())
        player = Player(id=secrets.token_urlsafe(6), name=name, connected=False)
        room.players[player.id] = player
        room.host_id = player.id
        room.total_scores[player.id] = 0
        if user_id is not None:
            room.accounts[player.id] = user_id
        if circle:  # what this host's last night left behind
            room.belt = str(circle.get("belt") or "")[:32]
            room.forfeits = [str(x)[:FORFEIT_MAX] for x in (circle.get("forfeits") or [])][:MAX_FORFEITS]
        self.rooms[room.code] = room
        self._scare(room, player.id, name)
        self._persist(room)
        return room, player, self._issue(room, player)

    def get(self, code: str) -> Room | None:
        if not isinstance(code, str) or not ROOM_CODE_RE.match(code):
            return None
        return self.rooms.get(code)

    def join_room(self, code: str, name: str, user_id: int | None = None) -> tuple[Room, Player, str]:
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
        if user_id is not None:
            room.accounts[player.id] = user_id
        room.last_active = self.clock()
        self._scare(room, player.id, name)
        self._persist(room)
        return room, player, self._issue(room, player)

    def _scare(self, room: Room, pid: str, name: str | None = None) -> None:
        """Queue a jump scare for this person if their name is on the (private) list. With a name, it's
        their arrival; without, it's a score screen for someone already matched."""
        if not self.prank_targets:
            return
        if name is not None:
            if not prank.matches(name, self.prank_targets):
                return
        elif pid not in room.scares:
            return
        room.scares[pid] = room.scares.get(pid, 0) + 1
        if name is not None:  # and a walk-on the whole room sees
            room.entrance = {"id": room.entrance.get("id", 0) + 1, "pid": pid, "name": name}

    def _scare_everyone_matched(self, room: Room) -> None:
        for pid in list(room.scares):
            if pid in room.players or pid in room.audience:
                self._scare(room, pid)

    @staticmethod
    def _name_free(room: Room, name: str) -> None:
        taken = [*(p.name for p in room.players.values()), *(w.name for w in room.audience.values())]
        if any(n.casefold() == name.casefold() for n in taken):
            raise HubError("name_taken", "Someone already has that name", 409)

    def join_audience(self, code: str, name: str, user_id: int | None = None) -> tuple[Room, Watcher, str]:
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
        if user_id is not None:
            room.accounts[watcher.id] = user_id
        room.last_active = self.clock()
        self._scare(room, watcher.id, name)
        self._persist(room)
        token = sign_token(self.settings.secret_key, watcher.id, room.code, self.settings.token_ttl_seconds)
        return room, watcher, token

    def hosting(self, user_ids: set[int]) -> dict[int, str]:
        """Rooms these accounts are hosting right now that a friend could walk into: account -> code."""
        out: dict[int, str] = {}
        for room in self.rooms.values():
            uid = room.accounts.get(room.host_id)
            if (
                uid in user_ids
                and not room.locked
                and room.phase == "lobby"
                and len(room.players) < self.settings.max_players_per_room
                and room.players[room.host_id].connected
            ):
                out[uid] = room.code
        return out

    def link_account(self, room: Room, pid: str, user_id: int) -> None:
        """A guest who signed in after sitting down: their seat now belongs to their account."""
        if pid in room.accounts or not (pid in room.players or pid in room.audience):
            return
        room.accounts[pid] = user_id
        self._persist(room)

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
        self._persist(room)
        token = sign_token(self.settings.secret_key, vid, room.code, self.settings.token_ttl_seconds)
        return room, token

    def is_member(self, room: Room, pid: str) -> bool:
        return pid in room.players or pid in room.viewers or pid in room.audience

    def cleanup(self) -> None:
        now = self.clock()
        gone = []
        for code, room in list(self.rooms.items()):
            idle = not room.conns and now - room.last_active > self.settings.room_idle_seconds
            old = now - room.created > self.settings.room_max_age_seconds
            if idle or old:
                del self.rooms[code]
                gone.append(code)
        if gone and self.store is not None and self.store.ready:
            with contextlib.suppress(RuntimeError):  # no running loop (sync tests): nothing was saved
                task = asyncio.get_running_loop().create_task(self.store.delete_snapshots(gone))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

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
            "chat": self._chat_view(room, pid),
            "call": {
                "available": calls.enabled(self.settings),
                "allowed": self._call_allowed(room, pid),
                "hush": room.call_hush,
            },
            "faces": room.faces,
            "night": self._night_view(room),
            "entrance": room.entrance or None,
            "crowd": self._crowd_view(room, pid),
            "market": self._market_view(room, pid),
            "cards": self._cards_view(room, pid),
            "rivals": {
                "pairs": [list(p) for p in room.rivals] if room.phase in ("game", "results") else [],
                "news": room.rival_news if room.phase == "results" else [],
                "bonus": showlib.RIVAL_BONUS,
            },
            "season": {"number": room.season_no, "table": room.season} if room.season_no else None,
            "intro": self._intro_view(room) if room.phase == "intro" else None,
            "teams": self._teams_view(room, pid),
            "ready": self._ready_view(room),
            "last_standings": room.last_standings if room.phase == "lobby" else [],
            "scare": room.scares.get(pid, 0),  # only ever this viewer's own count
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
            "how_to": list(room.game.HOW_TO) if game_view is not None and room.game is not None else [],
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
            "can_rematch": bool(room.last_show),
        }

    def _split_teams(self, room: Room, cls: type[Game]) -> dict[str, int]:
        """Everyone online, shuffled into two teams as even as can be."""
        if not cls.TEAMS:
            raise HubError("no_teams", f"{cls.title} has no team mode")
        online = [p.id for p in room.connected_players()]
        if len(online) < TEAM_MIN_PLAYERS:
            raise HubError("too_few", f"Teams need {TEAM_MIN_PLAYERS} or more players online")
        self.rng.shuffle(online)
        return {pid: i % 2 for i, pid in enumerate(online)}

    def _teams_view(self, room: Room, pid: str) -> dict[str, Any] | None:
        teams = room.intro.get("teams") if room.phase == "intro" else room.teams
        if not teams:
            return None
        return {
            "members": [[p for p, t in teams.items() if t == side] for side in (0, 1)],
            "you": teams.get(pid),
            "news": room.team_news if room.phase in ("results", "finale") else None,
        }

    def _intro_view(self, room: Room) -> dict[str, Any]:
        gid = room.intro.get("game", "")
        cls = Jackpot if gid == "jackpot" else REGISTRY.get(gid)
        online = [p.id for p in room.connected_players()]
        return {
            "game": gid,
            "title": cls.title if cls else gid,
            "blurb": cls.blurb if cls else "",
            "how_to": list(cls.HOW_TO) if cls else [],
            "options": dict(room.intro.get("options", {})),
            "closes_in": max(0.0, room.intro_until - self.clock()),
            "ready": sorted(p for p in room.ready if p in online),
            "needed": len(online),
        }

    def _ready_view(self, room: Room) -> dict[str, Any]:
        """A results/briefing screen everyone can skip together."""
        g = room.game
        open_ = room.phase == "game" and g is not None and not g.finished and g.phase in g.READING
        votes = sorted(room.ready) if open_ and room.ready_stage == (g.stage if g else "") else []
        return {
            "open": open_,
            "stage": g.stage if open_ and g is not None else "",
            "votes": votes,
            "needed": len([p for p in g.player_ids if room.players.get(p) and room.players[p].connected])
            if open_ and g is not None
            else 0,
        }

    @staticmethod
    def _standing(room: Room) -> tuple[str | None, str | None]:
        """(the clear leader, the last-placed player) by tonight's totals; None while nothing separates
        them (no points yet, or a tie at the top)."""
        totals = {p: room.total_scores.get(p, 0) for p in room.players}
        if len(totals) < 2 or len(set(totals.values())) < 2:
            return None, None
        top = max(totals.values())
        leaders = [p for p, t in totals.items() if t == top]
        low = min(totals.values())
        return (leaders[0] if len(leaders) == 1 else None), min(p for p, t in totals.items() if t == low)

    def _night_view(self, room: Room) -> dict[str, Any]:
        """The champion's belt and the loser's wheel."""
        holder = next(
            (p.id for p in room.players.values() if p.name.casefold() == room.belt.casefold()), None
        )
        leader, last = self._standing(room)
        return {
            "belt": {"name": room.belt, "holder": holder if room.belt else None},
            "leader": leader,
            "last": last,
            "forfeits": list(room.forfeits),
            "wheel": room.wheel or None,
        }

    def _keep_circle(self, room: Room) -> None:
        uid = room.accounts.get(room.host_id)
        if self.save_circle is None or uid is None:
            return
        task = asyncio.get_running_loop().create_task(self.save_circle(uid, room.belt, list(room.forfeits)))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _night(self, room: Room, pid: str, kind: str, msg: dict[str, Any]) -> bool:
        """Between games: crown tonight's champion, edit the forfeits, spin the loser's wheel."""
        is_host = pid == room.host_id
        if room.phase in ("game", "intro", "market"):
            raise HubError("in_progress", "Wait until the game is over", 409)
        leader, last = self._standing(room)
        if kind == "crown":
            if not is_host:
                raise HubError("not_host", "Only the host hands out the belt", 403)
            if leader is None:
                raise HubError("no_leader", "Nobody is clearly in front yet")
            name = room.players[leader].name
            room.belt = name
            room.entrance = {
                "id": room.entrance.get("id", 0) + 1,
                "pid": leader,
                "name": name,
                "kind": "belt",
            }
            self._keep_circle(room)
            return True
        if kind == "forfeit":
            if not is_host:
                raise HubError("not_host", "Only the host edits the forfeits", 403)
            if "del" in msg:
                i = msg["del"]
                if type(i) is not int or not 0 <= i < len(room.forfeits):
                    raise HubError("bad_message", "Unknown message")
                del room.forfeits[i]
            else:
                text = clean_chat(msg.get("add"))
                if len(text) > FORFEIT_MAX:
                    raise HubError("too_long", f"Forfeits are up to {FORFEIT_MAX} characters")
                if len(room.forfeits) >= MAX_FORFEITS:
                    raise HubError("full", "That's plenty of forfeits")
                if text.casefold() in (f.casefold() for f in room.forfeits):
                    raise HubError("duplicate", "That one's already on the wheel")
                room.forfeits.append(text)
            self._keep_circle(room)
            return True
        # the wheel: the loser spins it themselves (the host can do it for them)
        if last is None:
            raise HubError("no_loser", "Nobody is clearly last yet")
        if not is_host and pid != last:
            raise HubError("not_yours", "Only last place (or the host) spins the wheel", 403)
        now = self.clock()
        if now - room.call_last.get("wheel", -1e9) < WHEEL_GAP:
            raise HubError("slow_down", "The wheel is still spinning")
        room.call_last["wheel"] = now
        spare = [f for f in DEFAULT_FORFEITS if f.casefold() not in {x.casefold() for x in room.forfeits}]
        self.rng.shuffle(spare)
        pool = list(room.forfeits)
        self.rng.shuffle(pool)
        options = (pool + spare)[:WHEEL_SLOTS] if len(pool) < WHEEL_SLOTS else pool[:WHEEL_SLOTS]
        self.rng.shuffle(options)
        room.wheel = {
            "n": room.wheel.get("n", 0) + 1,
            "pid": last,
            "name": room.players[last].name,
            "options": options,
            "pick": self.rng.randrange(len(options)),
        }
        return True

    def _cards_view(self, room: Room, pid: str) -> dict[str, Any] | None:
        s = room.show
        if s is None and not room.accounts:
            return None
        this_game = self._plays(room) if room.phase == "game" else []
        played = next((p for p in s.plays if p["pid"] == pid), None) if s else None
        boost = next((p for p in this_game if p.get("bought") and p["pid"] == pid), None)
        return {
            "catalog": showlib.CARDS,
            "in_play": len(this_game),  # how many cards are down this game: never whose or which
            "news": room.card_news if room.phase == "results" else [],  # the reveal
            "coins": room.coin_news if room.phase in ("results", "finale") else {},
            "you": {
                "card": s.cards.get(pid) if s else None,
                "played": played["card"] if played else None,
                "peek": (s.peeks.get(pid) if s else None) or room.boost_peeks.get(pid),
                "signed_in": pid in room.accounts,  # can use power-ups bought with coins
                "boost": boost["card"] if boost else None,  # the one used this game
            }
            if pid in room.players
            else None,
        }

    def _plays(self, room: Room) -> list[dict[str, Any]]:
        """Every card and power-up played on the current game."""
        s = room.show
        shown = [p for p in s.plays if p["game"] == len(s.games)] if s is not None else []
        return shown + [b for b in room.boosts if b["game"] == room.game_no]

    async def _use_boost(self, room: Room, pid: str, msg: dict[str, Any]) -> None:
        """Use a power-up bought with coins on the game being played: one per player per game."""
        item = msg.get("item")
        target = msg.get("target")
        async with room.lock:
            game_no = self._check_boost(room, pid, item, target)
        user_id = room.accounts[pid]
        if self.spend_powerup is None or not await self.spend_powerup(user_id, str(item)):
            raise HubError("no_powerup", "You don't have that power-up. Buy one in the shop")
        async with room.lock:
            try:
                if room.game_no != game_no:
                    raise HubError("too_late", "That game has finished")
                self._check_boost(room, pid, item, target)
                play: dict[str, Any] = {"pid": pid, "card": item, "game": game_no, "bought": True}
                if item == "steal":
                    play["target"] = target
                if item == "peek":
                    seen = room.game.peek(pid) if room.game is not None else None
                    if not seen:
                        raise HubError("nothing_to_peek", "Nothing to peek at in this game right now")
                    room.boost_peeks[pid] = seen
                room.boosts = [b for b in room.boosts if b["game"] == game_no] + [play]
            except Exception:
                if self.refund_powerup is not None:
                    await self.refund_powerup(user_id, str(item))
                raise

    def _check_boost(self, room: Room, pid: str, item: Any, target: Any) -> int:
        game = room.game
        if pid not in room.accounts:
            raise HubError("signed_out", "Sign in to use power-ups")
        if room.phase != "game" or game is None or game.finished or game.game_id == "jackpot":
            raise HubError("no_card", "Power-ups are used during a game")
        if pid not in game.player_ids:
            raise HubError("no_card", "You're not in this game")
        if item not in coinlib.POWERUP_PRICES:
            raise HubError("bad_item", "That's not a power-up")
        if any(b["pid"] == pid and b["game"] == room.game_no for b in room.boosts):
            raise HubError("already_used", "One power-up per game")
        if item in showlib.EARLY_CARDS and not self._predict_open(room):
            raise HubError("too_late", "That one only works before the first round is over")
        if item == "steal" and (
            not isinstance(target, str) or target == pid or target not in game.player_ids
        ):
            raise HubError("bad_target", "Pick a rival in this game")
        return room.game_no

    def _pay_coins(self, room: Room, game: Game, scores: dict[str, int]) -> None:
        """Coins for every signed-in finisher (one result per account), paid in the background."""
        if self.on_results is None or game.game_id == "jackpot" or not room.accounts:
            return
        if room.teams:  # teams: everyone finishes where their team does
            totals = {t: sum(v for p, v in scores.items() if room.teams.get(p) == t) for t in (0, 1)}
            team_place = coinlib.places({str(t): v for t, v in totals.items()})
            placed = {p: team_place[str(room.teams[p])] for p in scores if p in room.teams}
        else:
            placed = coinlib.places(scores)
        best: dict[int, dict[str, Any]] = {}
        for pid, place in placed.items():
            uid = room.accounts.get(pid)
            if uid is None:
                continue
            row = {
                "user_id": uid,
                "pid": pid,
                "game_id": game.game_id,
                "place": place,
                "players": len(scores),
                "points": scores[pid],
                "coins": coinlib.coins_for(place, len(scores)),
            }
            if uid not in best or place < best[uid]["place"]:
                best[uid] = row
        if not best:
            return
        try:
            task = asyncio.get_running_loop().create_task(
                self._coins_landed(room, room.game_no, list(best.values()))
            )
        except RuntimeError:
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _coins_landed(self, room: Room, game_no: int, rows: list[dict[str, Any]]) -> None:
        if self.on_results is None:
            return
        try:
            paid = await self.on_results(rows)
        except Exception:
            log.exception("could not pay coins")
            return
        if room.game_no != game_no:
            return
        room.coin_news = {r["pid"]: {"place": r["place"], "coins": paid.get(r["user_id"], 0)} for r in rows}
        await self.broadcast(room)

    def _market_view(self, room: Room, pid: str) -> dict[str, Any] | None:
        m = room.show.market if room.show else None
        if m is None:
            return None
        titles = {gid: cls.title for gid, cls in REGISTRY.items()}
        finale = room.phase == "finale"
        mine = pid in room.players or pid in room.audience
        return {
            "open": room.phase == "market",
            "closes_in": max(0.0, room.market_until - self.clock()) if room.phase == "market" else None,
            "next": titles.get(room.market_next, room.market_next) if room.phase == "market" else "",
            "prices": dict(m.prices),
            "history": [dict(h) for h in m.history],
            "moves": dict(room.market_moves),
            "dividends": dict(room.market_dividends) if room.phase == "results" else {},
            "dividend": showlib.DIVIDEND,
            "trades": m.trades,
            # Your own book only; everyone's is revealed at the finale.
            "you": {
                # The audience is seated on their first trade: until then they hold the starting cash.
                "cash": m.cash.get(pid, showlib.START_CASH),
                "holdings": dict(m.holdings.get(pid, {})),
                "worth": m.worth(pid) if pid in m.cash else showlib.START_CASH,
                "tip": room.tip if pid == room.insider and room.phase == "market" else "",
            }
            if mine
            else None,
            # Audience traders, named at the finale so their books can be shown.
            "crowd": {w.id: w.name for w in room.audience.values() if w.id in m.cash} if finale else {},
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
            if room.game is not None and room.phase in ("game", "results")
            else [],
            "picks": picks,  # how many of the crowd back each player this game (never who)
            "open": self._predict_open(room),
            "you_picked": room.predictions.get(pid),
            "mvp": {
                "open": self._mvp_open(room),
                "you_voted": room.mvp_votes.get(pid),
                "votes": self._tally(room.mvp_votes),
                "bonus": FAN_BONUS,
            },
        }

    @staticmethod
    def _tally(votes: dict[str, str]) -> dict[str, int]:
        out: dict[str, int] = {}
        for target in votes.values():
            out[target] = out.get(target, 0) + 1
        return out

    @staticmethod
    def _mvp_open(room: Room) -> bool:
        return room.phase == "results" and room.show is not None and room.game is not None

    # -- outbound: one mailbox per connection, latest state wins ---------------------------------
    # Every frame is a full snapshot, so a connection only ever needs the newest one. If a send is
    # already in flight (slow or non-reading client), the next state just replaces the pending one
    # and the broadcaster moves on: a stuck socket can never stall the players who are acting.
    # Pen strokes (drawing games) are the exception: they queue in order and go out before the next
    # snapshot, batched into one frame per canvas. A screen too far behind is told to redraw instead.
    def _box(
        self, room: Room, pid: str, conn: Connection
    ) -> tuple[dict[str, Any], asyncio.Task[None] | None]:
        box = self._mail.get(conn)
        if box is not None:
            return box, None
        box = self._mail[conn] = {"pending": None, "ink": []}
        task = asyncio.get_running_loop().create_task(self._drain(room, pid, conn))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return box, task

    def _post(
        self, room: Room, pid: str, conn: Connection, data: dict[str, Any]
    ) -> asyncio.Task[None] | None:
        box, task = self._box(room, pid, conn)
        box["pending"] = data
        return task

    def _post_ink(self, room: Room, pid: str, conn: Connection, items: list[dict[str, Any]]) -> None:
        box, _ = self._box(room, pid, conn)
        box["ink"].extend(items)
        if len(box["ink"]) > INK_BACKLOG:
            box["ink"] = [{"resync": True}]

    @staticmethod
    def _ink_frames(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Consecutive strokes on one canvas share a frame: {"t": "ink", "id", "n": first, "ops"}. A whole
        drawing sent on request is marked "full" (an empty one has no ops)."""
        frames: list[dict[str, Any]] = []
        for it in items:
            last = frames[-1] if frames else None
            if "resync" in it:
                frames.append({"t": "ink", "resync": True})
            elif (
                last
                and last.get("id") == it["id"]
                and last["n"] + len(last["ops"]) == it["n"]
                and it.get("full") == last.get("full")
            ):
                last["ops"].append(it["op"])
            else:
                frame = {
                    "t": "ink",
                    "id": it["id"],
                    "n": it["n"],
                    "ops": [] if it.get("empty") else [it["op"]],
                }
                if it.get("full") or it.get("empty"):
                    frame["full"] = True
                frames.append(frame)
        return frames

    async def _drain(self, room: Room, pid: str, conn: Connection) -> None:
        box = self._mail[conn]
        try:
            while box["pending"] is not None or box["ink"]:
                if box["ink"]:
                    items, box["ink"] = box["ink"], []
                    for frame in self._ink_frames(items):
                        await asyncio.wait_for(conn.send_json(frame), timeout=self.send_timeout)
                    continue
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
        self._persist(room)  # every change is broadcast, so every change is saved
        tasks = [
            task
            for pid, conn in self._targets(room)
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
            if kind == "inksync":
                return self._ink_sync(room, pid, conn, msg)
            if kind == "call":
                return await self._call(room, pid, conn)
            if kind != "ping":
                await self.send_error(conn, "read_only", "TV mode is read-only")
            return
        if pid in room.audience and kind not in AUDIENCE_MESSAGE_TYPES:
            return await self.send_error(conn, "audience_only", "The audience can react and predict")
        room.last_active = self.clock()
        if kind == "ping":
            return
        try:
            if kind == "inksync":
                return self._ink_sync(room, pid, conn, msg)
            if kind == "call":
                return await self._call(room, pid, conn)
            if kind == "ink":
                return await self._ink(room, pid, conn, msg)
            if kind == "boost":
                await self._use_boost(room, pid, msg)
                return await self.broadcast(room)
            async with room.lock:
                changed = self._apply(room, pid, kind, msg)
            if changed:
                await self.broadcast(room)
        except (GameError, HubError) as exc:
            await self.send_error(conn, exc.code, exc.message)

    # Drawing games expose: ink(pid, msg) -> the canvas the stroke went on; canvas_for(pid) -> the live
    # canvas a screen shows (strokes are relayed only to screens showing that canvas, so a secret drawing
    # stays secret); and optionally drawing(pid, id) -> a finished drawing that screen may look at.
    async def _ink(self, room: Room, pid: str, conn: Connection, msg: dict[str, Any]) -> None:
        """A pen stroke from the artist: checked by the game, then relayed to the screens watching it."""
        async with room.lock:
            game = room.game
            draw = getattr(game, "ink", None)
            if room.phase != "game" or game is None or draw is None:
                raise HubError("no_canvas", "Nothing to draw on")
            canvas = draw(pid, msg)
            item = {"id": canvas.id, "n": len(canvas.ops) - 1, "op": canvas.ops[-1]}
            for to, c in self._targets(room):
                if c is not conn and game.canvas_for(to) is canvas:  # type: ignore[attr-defined]
                    self._post_ink(room, to, c, [item])
        self._persist(room)
        await asyncio.sleep(0)

    def _ink_sync(self, room: Room, pid: str, conn: Connection, msg: dict[str, Any]) -> None:
        """A screen that missed strokes (or just arrived) gets the whole drawing again; with an id, a
        finished drawing it is allowed to see (e.g. a page of the Draw Telephone album)."""
        game = room.game if room.phase == "game" else None
        if game is None or not hasattr(game, "canvas_for"):
            return
        want = msg.get("id")
        if want is None:
            canvas = game.canvas_for(pid)
        elif isinstance(want, str) and len(want) <= 16 and hasattr(game, "drawing"):
            canvas = game.drawing(pid, want)
        else:
            return
        if canvas is None:
            return
        box, _ = self._box(room, pid, conn)
        full = [{"id": canvas.id, "n": i, "op": op, "full": True} for i, op in enumerate(canvas.ops)]
        if not full:
            full = [{"id": canvas.id, "n": 0, "empty": True}]
        box["ink"] = [it for it in box["ink"] if it.get("id") != canvas.id] + full

    @staticmethod
    def _targets(room: Room) -> list[tuple[str, Connection]]:
        return [
            *room.conns.items(),
            *((v, c) for v, c in room.viewers.items() if c is not None),
            *((w.id, w.conn) for w in room.audience.values() if w.conn is not None),
        ]

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
        room.ready, room.ready_stage, room.last_standings = set(), "", []
        room.predictions, room.highlights, room.quip = {}, [], ""
        room.card_news, room.rival_news, room.rivals, room.mvp_votes = [], [], [], {}
        room.game_no += 1
        room.boost_peeks, room.coin_news, room.team_news = {}, {}, {}
        room.chat = [m for m in room.chat if m["team"] is None]  # new game, new teams: old team talk goes
        s = room.show
        if s is not None:
            s.peeks.clear()
            if game.game_id != "jackpot":
                showlib.deal_cards(s, game.player_ids, self.rng)
                room.rivals = showlib.rivals(room.total_scores, game.player_ids, self.rng)
        if self.on_game_started and game.game_id in REGISTRY:  # top up content in the background
            try:
                self.on_game_started(game.game_id, room.theme)
            except Exception:
                log.exception("on_game_started failed")

    def _award_mvp(self, room: Room) -> None:
        """The audience's MVP of the game that just ended: +FAN_BONUS each for the top vote (ties share)."""
        votes = self._tally(room.mvp_votes)
        room.mvp_votes = {}
        if not votes or room.show is None:
            return
        top = max(votes.values())
        names = room.names()
        for pid in (p for p, v in votes.items() if v == top and p in room.players):
            room.total_scores[pid] = room.total_scores.get(pid, 0) + FAN_BONUS
            title = room.show.games[-1]["title"] if room.show.games else ""
            room.show.reel.append(
                {
                    "icon": "⭐",
                    "title": "Fan favourite",
                    "text": f"The crowd voted {names.get(pid, '?')} MVP (+{FAN_BONUS})",
                    "game": title,
                }
            )

    def _start_next(self, room: Room, s: showlib.Show) -> None:
        """Start the show's next segment, or close the show with the finale."""
        self._award_mvp(room)
        nxt = s.next_game()
        if nxt == "jackpot":
            self._open_intro(room, "jackpot", slot="jackpot")
        elif nxt is not None:
            self._make_game(room, REGISTRY[nxt])  # raises (e.g. too few players) before anything moves
            if s.market is not None:
                self._open_market(room, nxt)
            else:
                self._open_intro(room, nxt, slot="playlist")
        else:
            self._finale(room, s)

    def _open_intro(
        self,
        room: Room,
        game_id: str,
        options: dict[str, str] | None = None,
        slot: str = "",
        teams: dict[str, int] | None = None,
    ) -> None:
        """The "how to play" screen. The game is built (and its clocks start) only when it ends."""
        room.intro = {
            "game": game_id,
            "options": dict(options or {}),
            "slot": slot,
            "teams": dict(teams or {}),
        }
        room.ready = set()
        room.predictions, room.highlights, room.quip = {}, [], ""
        if self.intro_seconds <= 0:
            self._close_intro(room)
            return
        room.game, room.phase = None, "intro"
        room.intro_until = self.clock() + self.intro_seconds

    def _close_intro(self, room: Room) -> None:
        i, s = room.intro, room.show
        if not i:
            return
        room.intro, room.ready = {}, set()
        teams: dict[str, int] = {}
        try:
            if i["game"] == "jackpot":
                stakes = {p.id: room.total_scores.get(p.id, 0) for p in room.players.values()}
                game = self._make_game(room, Jackpot, stakes=stakes)
            else:
                teams = i.get("teams") or {}
                game = self._make_game(room, REGISTRY[i["game"]], options=i["options"], teams=teams)
        except (GameError, HubError):
            # Someone left during the intro and the game can't run.
            if s is not None and i["slot"] == "playlist":
                s.started += 1
                room.phase = "results"
                self._start_next(room, s)
            elif s is not None and i["slot"] == "jackpot":
                s.jackpot_played = True
                room.phase = "results"
                self._start_next(room, s)
            else:
                room.game, room.phase = None, "lobby"
            return
        # Only the host's Teams switch makes room teams (Codewords keeps its own red/blue in game.teams).
        room.teams = {p: t for p, t in teams.items() if p in game.round_scores}
        self._begin(room, game)
        if s is not None and i["slot"] == "playlist":
            s.started += 1
        elif s is not None and i["slot"] == "jackpot":
            s.jackpot_played = True

    def _open_market(self, room: Room, game_id: str) -> None:
        """Trading window before a show game. The game itself is built when the bell rings."""
        market = room.show.market if room.show else None
        room.insider, room.tip = "", ""
        if market is not None:
            for pid in room.players:
                market.seat(pid)
            online = [p.id for p in room.connected_players()]
            if online:  # one random player gets an insider tip: someone else's secret book
                room.insider = self.rng.choice(online)
                names = room.names() | {w.id: w.name for w in room.audience.values()}
                room.tip = market.tip(room.insider, self.rng, names)
        room.game, room.phase = None, "market"
        room.market_next = game_id
        room.market_until = self.clock() + MARKET_SECONDS
        room.predictions, room.highlights, room.quip = {}, [], ""

    def _close_market(self, room: Room) -> None:
        s = room.show
        if s is None or room.phase != "market":
            return
        self._open_intro(room, room.market_next, slot="playlist")

    def _start_show(self, room: Room, games: list[str], jackpot: bool, market: bool) -> None:
        game = self._make_game(room, REGISTRY[games[0]])  # raises before anything changes
        room.total_scores = {p: 0 for p in room.players}  # a new show, a fresh scoreboard
        room.last_show = {"games": list(games), "jackpot": jackpot, "market": market}
        del game  # only built to check the room can play it
        if market:
            room.show = showlib.Show(playlist=list(games), jackpot=jackpot, market=showlib.Market())
            self._open_market(room, games[0])
        else:
            room.show = showlib.Show(playlist=list(games), jackpot=jackpot)
            self._open_intro(room, games[0], slot="playlist")

    def _ready(self, room: Room, pid: str, msg: dict[str, Any]) -> bool:
        """Ready votes: on the intro, everyone online starts the game; on a results/briefing screen,
        everyone in the game moves it on. Nobody can be rushed: it takes every single vote."""
        if pid not in room.players:
            raise HubError("players_only", "Only contestants can do that")
        online = {p.id for p in room.connected_players()}
        if room.phase == "intro":
            room.ready.add(pid)
            if online <= room.ready:
                self._close_intro(room)
            return True
        g = room.game
        if room.phase != "game" or g is None or g.finished or g.phase not in g.READING:
            raise HubError("not_now", "Nothing to skip right now")
        seen = msg.get("stage")
        if not isinstance(seen, str) or seen != g.stage:
            return False  # that screen already moved on
        if pid not in g.player_ids:
            raise HubError("players_only", "You're not in this game")
        if room.ready_stage != g.stage:
            room.ready_stage, room.ready = g.stage, set()
        room.ready.add(pid)
        if {p for p in g.player_ids if p in online} <= room.ready:
            room.ready, room.ready_stage = set(), ""
            g.advance()
            self._maybe_finish(room)
        return True

    def _play_card(self, room: Room, pid: str, msg: dict[str, Any]) -> bool:
        """Play your one power card on the game being played. Secret until that game's results."""
        s, game = room.show, room.game
        if pid not in room.players or s is None or game is None or room.phase != "game":
            raise HubError("no_card", "Cards are played during a show game")
        if game.game_id == "jackpot" or game.finished:
            raise HubError("no_card", "No cards in this game")
        if pid not in game.player_ids:
            raise HubError("no_card", "You're not in this game")
        card = s.cards.get(pid)
        if card is None:
            raise HubError("no_card", "You've played your card this show")
        play: dict[str, Any] = {"pid": pid, "card": card, "game": len(s.games)}
        if card in showlib.EARLY_CARDS and not self._predict_open(room):
            raise HubError("too_late", "That card only works before the first round is over")
        if card == "steal":
            target = msg.get("target")
            if not isinstance(target, str) or target == pid or target not in game.player_ids:
                raise HubError("bad_target", "Pick a rival in this game")
            play["target"] = target
        if card == "peek":
            try:
                seen = game.peek(pid)
            except Exception:  # a peek bug must never break the game
                log.exception("peek failed")
                seen = None
            if not seen:
                raise HubError("nothing_to_peek", "Nothing to peek at right now. Try again in a moment")
            s.peeks[pid] = seen
        del s.cards[pid]
        s.plays.append(play)
        return True

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
        if s.market is not None:
            fans = {w.id: w for w in room.audience.values() if w.id in s.market.cash}
            if fans:
                best = max(fans, key=s.market.worth)
                if s.market.worth(best) > showlib.START_CASH:
                    s.awards.append(
                        {
                            "icon": "🤑",
                            "title": "Crowd tycoon",
                            "text": f"{fans[best].name} (audience) ended worth ${s.market.worth(best):,}",
                        }
                    )
        s.quip = room.quip = showlib.quip(
            totals, names, room.title or "the show", room.decks, self.rng, "show"
        )
        # The season: every show in this room adds to a running table (shows won, points).
        room.season_no += 1
        top = max(totals.values(), default=0)
        for pid, pts in totals.items():
            row = room.season.setdefault(pid, {"wins": 0, "points": 0})
            row["points"] += pts
            if pts == top:
                row["wins"] += 1
        self._scare_everyone_matched(room)
        room.game, room.phase = None, "finale"

    def _apply(self, room: Room, pid: str, kind: str, msg: dict[str, Any]) -> bool:
        is_host = pid == room.host_id
        if kind == "react":
            return self._react(room, pid, msg)
        if kind == "chat":
            return self._chat(room, pid, msg)
        if kind == "avatar":
            face, tone = msg.get("face"), msg.get("tone")
            if (
                type(face) is not int
                or type(tone) is not int
                or not (0 <= face < AVATAR_FACES and 0 <= tone < AVATAR_TONES)
            ):
                raise HubError("bad_message", "Unknown message")
            if room.faces.get(pid) == [face, tone]:
                return False
            room.faces[pid] = [face, tone]
            return True
        if kind == "hush":
            if not is_host:
                raise HubError("not_host", "Only the host can mute everyone", 403)
            now = self.clock()
            if now - room.call_last.get("hush", -1e9) < CALL_GAP:
                raise HubError("slow_down", "Everyone was just muted")
            room.call_last["hush"] = now
            room.call_hush += 1
            return True
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
            if room.phase in ("game", "intro", "market"):
                raise HubError("in_progress", "A game is already running", 409)
            cls = REGISTRY.get(msg.get("game")) if isinstance(msg.get("game"), str) else None
            if cls is None:
                raise HubError("bad_game", "Unknown game")
            options = self._options(cls, msg.get("options"))
            want_teams = msg.get("teams", False)
            if not isinstance(want_teams, bool):
                raise HubError("bad_message", "Unknown message")
            teams = self._split_teams(room, cls) if want_teams else {}
            # raises (too few players, a team rule) before anything changes
            self._make_game(room, cls, options=options, teams=teams)
            room.show = None  # a one-off game outside any show
            self._open_intro(room, cls.game_id, options, teams=teams)
            return True
        if kind == "shuffle":
            if not is_host:
                raise HubError("not_host", "Only the host can shuffle the teams", 403)
            if room.phase != "intro" or not room.intro.get("teams"):
                raise HubError("no_teams", "Teams are shuffled before a team game starts")
            cls = REGISTRY[room.intro["game"]]
            room.intro["teams"] = self._split_teams(room, cls)
            room.ready = set()
            return True
        if kind == "ready":
            return self._ready(room, pid, msg)
        if kind == "show":
            if not is_host:
                raise HubError("not_host", "Only the host can start a show", 403)
            if room.phase in ("game", "intro", "market"):
                raise HubError("in_progress", "A game is already running", 409)
            raw = msg.get("games")
            if (
                not isinstance(raw, list)
                or not showlib.MIN_GAMES <= len(raw) <= showlib.MAX_GAMES
                or any(not isinstance(g, str) or g not in REGISTRY or not REGISTRY[g].SHOW for g in raw)
                or len(set(raw)) != len(raw)
            ):
                raise HubError("bad_show", f"Pick {showlib.MIN_GAMES}-{showlib.MAX_GAMES} different games")
            jackpot = msg.get("jackpot", True)
            market = msg.get("market", False)
            if not isinstance(jackpot, bool) or not isinstance(market, bool):
                raise HubError("bad_message", "Unknown message")
            self._start_show(room, list(raw), jackpot, market)
            return True
        if kind == "rematch":
            if not is_host:
                raise HubError("not_host", "Only the host can start a rematch", 403)
            if room.phase != "finale" or not room.last_show:
                raise HubError("no_show", "Rematches start from a show's finale")
            ls = room.last_show
            self._start_show(room, list(ls["games"]), ls["jackpot"], ls["market"])
            return True
        if kind == "card":
            return self._play_card(room, pid, msg)
        if kind == "mvp":
            if pid not in room.audience:
                raise HubError("audience_only", "Only the audience votes for MVP")
            if not self._mvp_open(room) or room.game is None:
                raise HubError("mvp_closed", "MVP voting is closed")
            target = msg.get("target")
            if not isinstance(target, str) or target not in room.game.player_ids:
                raise HubError("bad_target", "Pick a contestant")
            room.mvp_votes[pid] = target
            return True
        if kind == "trade":
            market = room.show.market if room.show else None
            trader_ok = pid in room.players or pid in room.audience
            if not trader_ok or market is None or room.phase != "market":
                raise HubError("market_closed", "The market is closed")
            target, qty = msg.get("target"), msg.get("qty")
            if not isinstance(target, str) or target not in room.players:
                raise HubError("bad_trade", "Pick a player to trade")
            if isinstance(qty, bool) or not isinstance(qty, int):
                raise HubError("bad_trade", "Trade a whole number of shares")
            market.seat(pid, listed=pid in room.players)
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
            if room.phase == "intro":  # the host starts the game now
                self._close_intro(room)
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
            if room.phase == "finale":  # keep the final standings on the lobby screen
                room.last_standings = sorted(
                    (
                        {"id": p.id, "name": p.name, "total": room.total_scores.get(p.id, 0)}
                        for p in room.players.values()
                    ),
                    key=lambda r: -r["total"],
                )
            room.intro, room.ready = {}, set()
            room.game, room.phase, room.show = None, "lobby", None
            room.highlights, room.quip, room.predictions = [], "", {}
            room.rivals, room.rival_news, room.card_news, room.mvp_votes = [], [], [], {}
            return True
        if kind in ("crown", "forfeit", "wheel"):
            if pid not in room.players:
                raise HubError("players_only", "Only contestants can do that")
            return self._night(room, pid, kind, msg)
        if kind in ("kick", "lock", "title"):
            if not is_host:
                raise HubError("not_host", "Only the host can do that", 403)
            return self._host_tool(room, pid, kind, msg)
        if kind == "leave":
            player = room.players.get(pid)
            if player and room.phase == "lobby" and pid != room.host_id:
                del room.players[pid]
                room.total_scores.pop(pid, None)
                room.faces.pop(pid, None)
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
            self._drop_from_call(room, target)
            if watcher.conn is not None:
                asyncio.get_running_loop().create_task(watcher.conn.close(KICKED))
            return True
        if not isinstance(target, str) or target not in room.players or target == pid:
            raise HubError("bad_target", "Pick another player")
        if room.phase == "game":
            raise HubError("in_progress", "Remove players between games")
        del room.players[target]
        room.total_scores.pop(target, None)
        room.faces.pop(target, None)
        self._drop_from_call(room, target)
        conn = room.conns.pop(target, None)
        if conn is not None:
            asyncio.get_running_loop().create_task(conn.close(KICKED))
        return True

    def _drop_from_call(self, room: Room, pid: str) -> None:
        """The host removed someone: take them out of the call too (their pass expires on its own)."""
        if calls.enabled(self.settings):
            call_room = calls.room_name(self.settings, room.code, room.created)
            task = asyncio.get_running_loop().create_task(
                calls.remove_participant(self.settings, call_room, pid)
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

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

    # -- calls (LiveKit) ------------------------------------------------------------------------------
    @staticmethod
    def _call_allowed(room: Room, pid: str) -> bool:
        """Calls are for signed-in accounts; a TV may watch when the room's host is signed in."""
        return (room.host_id if pid in room.viewers else pid) in room.accounts

    async def _call(self, room: Room, pid: str, conn: Connection) -> None:
        """A pass for the room's voice/video call, sent only to the asking connection."""
        if not calls.enabled(self.settings):
            raise HubError("no_calls", "Calls aren't set up on this server")
        if not self._call_allowed(room, pid):
            raise HubError("sign_in", "Sign in to join the call")
        now = self.clock()
        if now - room.call_last.get(pid, -1e9) < CALL_GAP:
            raise HubError("slow_down", "Joining the call already: give it a moment")
        room.call_last[pid] = now
        who = room.players.get(pid) or room.audience.get(pid)
        tv = pid in room.viewers
        name = "TV" if tv else who.name if who else "?"
        call_room = calls.room_name(self.settings, room.code, room.created)
        token = calls.join_token(self.settings, call_room, pid, name, can_publish=not tv)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(
                conn.send_json({"t": "call", "url": self.settings.livekit_url, "token": token, "tv": tv}), 5
            )

    # -- chat -----------------------------------------------------------------------------------------
    @staticmethod
    def _chat_game(room: Room) -> Game | None:
        return room.game if room.game is not None and room.phase in ("game", "results") else None

    def _chat(self, room: Room, pid: str, msg: dict[str, Any]) -> bool:
        to = msg.get("to", "all")
        if to not in ("all", "team"):
            raise HubError("bad_message", "Unknown chat channel")
        text = clean_chat(msg.get("text"))
        game = self._chat_game(room)
        seated = pid in room.players
        if game is not None and seated and pid in game.round_scores and game.chat_muted(pid):
            raise HubError("muted", game.CHAT_MUTED_NOTE)
        team = None
        if to == "team":
            channel = (
                game.chat_team(pid) if game is not None and seated and pid in game.round_scores else None
            )
            if channel is None:
                raise HubError("no_team", "There's no team chat right now")
            team = channel[0]
        now = self.clock()
        if now - room.chat_last.get(pid, -1e9) < CHAT_GAP:
            raise HubError("slow_down", "Slow down a little")
        burst, window = CHAT_ROOM_BURST
        room.chat_window = [t for t in room.chat_window if now - t < window]
        if len(room.chat_window) >= burst:
            raise HubError("slow_down", "The chat is busy: try again in a moment")
        room.chat_last[pid] = now
        room.chat_window.append(now)
        who = room.players.get(pid) or room.audience.get(pid)
        room.chat_seq += 1
        room.chat = [
            *room.chat[-(CHAT_KEEP - 1) :],
            {"id": room.chat_seq, "by": pid, "name": who.name if who else "?", "text": text, "team": team},
        ]
        return True

    def _chat_view(self, room: Room, pid: str) -> dict[str, Any]:
        """Everyone sees the room's messages; team messages only reach that team's current members."""
        game = self._chat_game(room)
        playing = game is not None and pid in room.players and pid in game.round_scores
        channel = game.chat_team(pid) if game is not None and playing else None
        mine = channel[0] if channel else None
        shown = [m for m in room.chat if m["team"] is None or (mine is not None and m["team"] == mine)]
        return {
            "messages": [
                {
                    "id": m["id"],
                    "by": m["by"],
                    "name": m["name"],
                    "text": m["text"],
                    "team": m["team"] is not None,
                }
                for m in shown[-CHAT_SHOWN * 2 :]
            ],
            "team": channel[1] if channel else None,
            "muted": bool(game is not None and playing and game.chat_muted(pid)),
            "muted_note": game.CHAT_MUTED_NOTE if game is not None else "",
            "can_send": pid not in room.viewers,
        }

    def _maybe_finish(self, room: Room) -> None:
        game = room.game
        if game is None or not game.finished or room.phase != "game":
            return
        scores = game.scores()
        s = room.show
        if game.game_id != "jackpot":
            scores, room.card_news = showlib.apply_cards(self._plays(room), scores)
        if s is not None and game.game_id != "jackpot":
            room.rival_news = showlib.settle_rivals(room.rivals, scores)
            for r in room.rival_news:
                if r["winner"] is not None:
                    scores[r["winner"]] = scores.get(r["winner"], 0) + showlib.RIVAL_BONUS
        for pid, pts in scores.items():
            room.total_scores[pid] = room.total_scores.get(pid, 0) + pts
        if room.teams:
            totals = [sum(v for p, v in scores.items() if room.teams.get(p) == t) for t in (0, 1)]
            room.team_news = {
                "scores": totals,
                "winner": 0 if totals[0] > totals[1] else 1 if totals[1] > totals[0] else None,
            }
        room.phase = "results"
        self._scare_everyone_matched(room)  # the scores are up: boo
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
            top = max(scores.values(), default=0)
            winners = [p for p, v in scores.items() if v == top] if scores else []
            room.market_dividends = room.show.market.pay_dividends(winners)
        if room.show is not None:
            room.show.games.append({"game": game.game_id, "title": game.title, "scores": dict(scores)})
            room.show.reel.extend({**h, "game": game.title} for h in room.highlights)
        if self.on_game_finished:
            try:
                self.on_game_finished(game.game_id, game.summary())
            except Exception:
                log.exception("failed to record game result")
        self._pay_coins(room, game, scores)

    # -- timers -------------------------------------------------------------
    async def tick(self) -> None:
        for room in list(self.rooms.values()):
            if room.phase == "market" and self.clock() >= room.market_until:
                async with room.lock:
                    self._close_market(room)
                await self.broadcast(room)
                continue
            if room.phase == "intro" and self.clock() >= room.intro_until:
                async with room.lock:
                    self._close_intro(room)
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

    # 0.2 s: timers (a Chicken Run bomb, a turn clock) fire within a fifth of a second of their time.
    async def run_ticker(self, interval: float = 0.2) -> None:
        while True:
            try:
                await self.tick()
                self.cleanup()
            except Exception:
                log.exception("ticker error")
            await asyncio.sleep(interval)
