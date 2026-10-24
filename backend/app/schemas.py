"""The HTTP API's response contract. Each route declares one of these as its response model, so the
OpenAPI document (exported to frontend/openapi.json) describes every body, and the web and mobile apps
generate their types from it instead of copying them by hand. Models forbid unknown fields:
tests/test_contract.py validates real responses against them, so a field added in a route but not
here fails the build.

The realtime contract lives here too: RoomFrame is the "state" message every screen receives over the
WebSocket (validated against every frame the room tests send). Each game's own view is still a plain
object inside it (`game`); those get their own models game by game.

Request bodies stay next to their routes (main.py, accounts.py)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorDetail(Strict):
    code: str
    message: str


class ErrorBody(Strict):
    """Every error: a stable machine code and a short message safe to show."""

    error: ErrorDetail


class Ok(Strict):
    ok: bool


# -- games and rooms ------------------------------------------------------------------------------------
class GameCard(Strict):
    id: str
    title: str
    blurb: str
    min_players: int
    max_players: int
    options: dict[str, list[str]]
    how_to: list[str]
    show: bool
    classic: bool
    teams: bool
    category: str
    featured: int | None
    ranked: bool


class RoomPass(Strict):
    """A seat (player or audience): the room code, your id in it, and the token the socket sends first."""

    code: str
    player_id: str
    token: str


class TvPass(Strict):
    code: str
    token: str


# -- accounts -------------------------------------------------------------------------------------------
class PublicUser(Strict):
    """Your own account (only ever sent to its owner)."""

    username: str
    coins: int
    powerups: dict[str, int]
    email: str | None
    email_verified: bool


class UserBody(Strict):
    user: PublicUser


class NewAccount(Strict):
    """Sign-up and recovery: the recovery code is shown once and never again."""

    user: PublicUser
    recovery_code: str


class Me(Strict):
    user: PublicUser | None
    accounts: bool  # false when the server has no database: sign-in is unavailable
    mail: bool  # true when the server can send email: email sign-in, reset links and notices


class MfaStatus(Strict):
    enabled: bool
    backup_codes_left: int


class MfaSetup(Strict):
    """Scan the QR code (rows of 1 = dark) or type the key into the authenticator app, then confirm."""

    secret: str
    uri: str
    qr: list[str]


class BackupCodes(Strict):
    """Shown once: each works once if the phone is lost."""

    codes: list[str]


class GameStat(Strict):
    played: int
    wins: int
    best: int
    coins: int


class Totals(Strict):
    played: int
    wins: int
    coins: int


class SeasonStat(Strict):
    id: str
    played: int
    wins: int
    points: int
    rank: int | None


class MyStats(Strict):
    games: dict[str, GameStat]
    totals: Totals
    season: SeasonStat


class FriendRow(Strict):
    username: str
    room: str | None  # a room they're hosting that you could walk into


class Friends(Strict):
    friends: list[FriendRow]
    sent: list[str]
    asked: list[str]


class ShopItem(Strict):
    id: str
    price: int
    name: str
    icon: str
    text: str


class Shop(Strict):
    items: list[ShopItem]


class LeaderRow(Strict):
    user_id: int
    username: str
    points: int
    wins: int
    played: int


class Leaderboard(Strict):
    season: str
    rows: list[LeaderRow]


# -- clubs -----------------------------------------------------------------------------------------------
class QuietHours(Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    starts: str = Field(alias="from")  # "23:00"
    ends: str = Field(alias="to")  # "08:00"


class ClubRules(Strict):
    games: list[str]  # the games the club plays; empty = all of them
    chat: bool
    battles: bool
    quiet: QuietHours | None  # no game notifications in these hours


class ClubSummary(Strict):
    slug: str
    name: str
    about: str
    role: str  # yours: owner, admin, moderator or member
    members: int


class ClubList(Strict):
    clubs: list[ClubSummary]


class ClubMember(Strict):
    username: str
    role: str
    joined_at: str  # ISO 8601


class ClubRoom(Strict):
    """A live room of the club, for members to walk into."""

    code: str
    host: str
    players: int
    phase: str
    game: str | None
    open: bool  # still in the lobby and not locked


class InviteInfo(Strict):
    id: int
    uses_left: int
    expires_at: str


class NewInvite(Strict):
    """The code is shown only now (only its hash is kept)."""

    id: int
    code: str
    path: str  # /join/<code>: the link to share
    uses_left: int
    expires_at: str


class ClubDetail(Strict):
    slug: str
    name: str
    about: str
    rules: ClubRules
    role: str
    member_count: int
    members: list[ClubMember]
    rooms: list[ClubRoom]
    invites: list[InviteInfo]  # live invite links: moderators and up only, else empty


# Spelled out, not taken from Python's HTTP status table: its wording changes between versions (422 is
# "Unprocessable Entity" in 3.12, "Unprocessable Content" in 3.13), which would change the contract.
ERROR_DESCRIPTIONS = {
    400: "Bad request",
    401: "Not signed in",
    403: "Not allowed",
    404: "Not found",
    409: "Conflict",
    422: "Invalid request",
    429: "Too many requests",
    503: "Unavailable",
}
ERRORS: dict[int | str, dict[str, object]] = {
    status: {"model": ErrorBody, "description": text} for status, text in ERROR_DESCRIPTIONS.items()
}


# -- realtime: the "state" frame every screen receives over the WebSocket --------------------------------
class Highlight(Strict):
    icon: str
    title: str
    text: str
    game: str | None = None  # set on the show's highlight reel


class CategoryInfo(Strict):
    id: str
    label: str
    title: str
    blurb: str


class RoomInfo(Strict):
    code: str
    phase: Literal["lobby", "intro", "market", "game", "results", "finale"]
    host: str
    title: str
    locked: bool
    theme: str


class PlayerRow(Strict):
    id: str
    name: str
    connected: bool
    host: bool
    total: int


class PlaylistItem(Strict):
    id: str
    title: str


class ShowGame(Strict):
    game: str
    title: str
    scores: dict[str, int]


class Show(Strict):
    playlist: list[PlaylistItem]
    jackpot: bool
    started: int
    next: str | None
    finished: bool
    games: list[ShowGame]
    reel: list[Highlight]
    awards: list[Highlight]
    market: bool
    can_rematch: bool


class ChatMessage(Strict):
    id: int
    by: str
    name: str
    text: str
    team: bool


class Chat(Strict):
    messages: list[ChatMessage]
    team: str | None
    muted: bool
    muted_note: str
    can_send: bool


class Call(Strict):
    available: bool
    allowed: bool
    hush: int


class Belt(Strict):
    name: str
    holder: str | None


class Wheel(Strict):
    n: int
    pid: str
    name: str
    options: list[str]
    pick: int


class Night(Strict):
    belt: Belt
    leader: str | None
    last: str | None
    forfeits: list[str]
    wheel: Wheel | None


class Entrance(Strict):
    id: int
    pid: str
    name: str
    kind: str | None = None  # "belt" when the champion walks on


class CrowdMember(Strict):
    id: str
    name: str
    points: int
    connected: bool


class Contestant(Strict):
    id: str
    name: str


class Mvp(Strict):
    open: bool
    you_voted: str | None
    votes: dict[str, int]
    bonus: int


class Crowd(Strict):
    members: list[CrowdMember]
    contestants: list[Contestant]
    picks: dict[str, int]
    open: bool
    you_picked: str | None
    mvp: Mvp


class MarketBook(Strict):
    cash: int
    holdings: dict[str, int]
    worth: int
    tip: str


class Market(Strict):
    open: bool
    closes_in: float | None
    next: str
    prices: dict[str, int]
    history: list[dict[str, int]]
    moves: dict[str, float]
    dividends: dict[str, int]
    dividend: int
    trades: int
    you: MarketBook | None
    crowd: dict[str, str]
    worth: dict[str, int]
    books: dict[str, dict[str, int]]
    bonus: dict[str, int]


class CardInfo(Strict):
    name: str
    icon: str
    text: str


class CardPlay(Strict):
    pid: str
    card: str
    game: int
    effect: int
    bought: bool = False  # a power-up bought with coins, not the show's free card
    target: str | None = None  # whom a Steal hit


class CoinNews(Strict):
    coins: int
    place: int


class CardsYou(Strict):
    card: str | None
    played: str | None
    peek: str | None
    signed_in: bool
    boost: str | None


class Cards(Strict):
    catalog: dict[str, CardInfo]
    in_play: int
    news: list[CardPlay]
    coins: dict[str, CoinNews]
    you: CardsYou | None


class RivalResult(Strict):
    players: list[str]
    winner: str | None


class Rivals(Strict):
    pairs: list[list[str]]
    news: list[RivalResult]
    bonus: int


class SeasonRow(Strict):
    wins: int
    points: int


class Season(Strict):
    number: int
    table: dict[str, SeasonRow]


class Intro(Strict):
    game: str
    title: str
    blurb: str
    how_to: list[str]
    options: dict[str, str]
    closes_in: float
    ready: list[str]
    needed: int


class TeamNews(Strict):
    scores: list[int]
    winner: int | None


class Teams(Strict):
    members: list[list[str]]
    you: int | None
    news: TeamNews | None


class Ready(Strict):
    open: bool
    stage: str
    votes: list[str]
    needed: int


class Standing(Strict):
    id: str
    name: str
    total: int


class Reaction(Strict):
    id: int
    by: str
    e: str


class RoomFrame(Strict):
    """The room as one screen sees it. Secrets are filtered per viewer before this is built."""

    t: Literal["state"]
    you: str
    tv: bool
    role: Literal["player", "audience", "tv"]
    room: RoomInfo
    themes: dict[str, str]
    show: Show | None
    highlights: list[Highlight]
    quip: str
    reactions: list[Reaction]
    chat: Chat
    call: Call
    faces: dict[str, list[int]]
    night: Night
    entrance: Entrance | None
    crowd: Crowd
    market: Market | None
    cards: Cards | None
    rivals: Rivals
    season: Season | None
    intro: Intro | None
    teams: Teams | None
    ready: Ready
    last_standings: list[Standing]
    scare: int
    players: list[PlayerRow]
    games: list[GameCard]
    categories: list[CategoryInfo]
    game: dict[str, Any] | None  # the game's own view (typed per game later)
    stage: str | None
    how_to: list[str]
