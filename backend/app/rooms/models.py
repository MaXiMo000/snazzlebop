"""Shared room types and limits: Room, Watcher, the connection protocol, name and chat cleaning."""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from dataclasses import MISSING, dataclass, field, fields
from typing import Any, Protocol

from .. import show as showlib
from ..games import Game, Player
from ..games.base import Deck

log = logging.getLogger("snazzlebop.rooms")

ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I/O: avoids lookalikes
ROOM_CODE_RE = re.compile(r"^[A-HJ-NP-Z]{3,8}$")
ALLOWED_MESSAGE_TYPES = {
    *("ping", "start", "act", "skip", "lobby", "leave", "kick", "lock", "title"),
    *(
        "show",
        "next",
        "theme",
        "react",
        "predict",
        "trade",
        "card",
        "mvp",
        "rematch",
        "ready",
        "boost",
        "power",
        "party",
    ),
    *("shuffle", "ink", "inksync", "chat", "call", "avatar", "hush", "crown", "forfeit", "wheel"),
}
TEAM_MIN_PLAYERS = 4  # two teams of at least two
HOST_GRACE = 300.0  # seconds a host may be away (app switched, phone locked) before someone takes over
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
CLUB_CHAT_OFF = "Chat is off in this club's rooms"
CHAT_ROOM_BURST = (12, 5.0)  # at most 12 messages per 5 seconds from the players
CHAT_AUDIENCE_BURST = (6, 5.0)  # and 6 from the whole audience
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
    audience_chat_window: list[float] = field(default_factory=list)
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
    club_id: int | None = None  # a club room: listed for that club's members
    # The club's rules when the room opened: the games it plays (empty = all) and whether chat is on.
    club_games: list[str] = field(default_factory=list)
    club_chat: bool = True
    # Safety. hidden: account -> accounts it must not hear from (blocks, either way), kept for the
    # people seated here. club_muted: account -> when a club moderator's mute ends (wall-clock time).
    hidden: dict[int, set[int]] = field(default_factory=dict)
    club_muted: dict[int, float] = field(default_factory=dict)
    # When the host's last screen dropped (None while they're here). Switching apps or locking a phone
    # drops the socket; the host keeps the room unless they stay away for HOST_GRACE seconds.
    host_away: float | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Accounts (private: never in any view): seat -> account id, for coins, stats and power-ups.
    accounts: dict[str, int] = field(default_factory=dict)
    game_no: int = 0  # games started in this room
    boosts: list[dict[str, Any]] = field(default_factory=list)  # power-ups bought with coins, as plays
    boost_peeks: dict[str, str] = field(default_factory=dict)  # what a bought Peek showed (private)
    coin_news: dict[str, dict[str, int]] = field(default_factory=dict)  # last game: pid -> place, coins
    teams: dict[str, int] = field(default_factory=dict)  # this game's teams (player -> 0/1); {} = no teams
    ranked: bool = False  # this game is rated (ratings.py): accounts only, fixed options, no power-ups
    rating_news: dict[str, dict[str, Any]] = field(default_factory=dict)  # last game: pid -> change
    # A battle waiting to be played here (battles.py): {"id", "game", "kind", "accounts": [ids]} ({} = none)
    battle: dict[str, Any] = field(default_factory=dict)
    battle_news: dict[str, dict[str, Any]] = field(default_factory=dict)  # last game: pid -> prize
    # Fair play (fairplay.py): when this game began, and the accounts seated in it then (only they're paid).
    game_began: float = -1.0  # -1: a room saved before this was tracked
    game_accounts: dict[str, int] = field(default_factory=dict)
    # Power-ups v2 (a game's own POWERS): who used one in which game, what everyone saw, and the line
    # each player's own power-up showed them alone.
    power_used: dict[str, int] = field(default_factory=dict)  # pid -> game_no
    power_news: list[dict[str, Any]] = field(default_factory=list)
    power_private: dict[str, str] = field(default_factory=dict)
    # Party items (party.py): the latest effects everyone plays, and when each player last used one.
    party_effects: list[dict[str, Any]] = field(default_factory=list)
    party_seq: int = 0
    party_last: dict[str, float] = field(default_factory=dict)
    react_logged: dict[str, int] = field(
        default_factory=dict
    )  # pid -> the game a reaction was last logged in
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
