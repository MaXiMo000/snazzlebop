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
    ranked_min: int | None  # players a ranked game needs (None: not played ranked)


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
    has_password: bool  # false for an account that signs in only with Google
    plus_until: str | None  # Snazzlebop Plus is on until then (ISO 8601); None: not a member
    plus: bool  # every Plus perk is on: paid, or a confirmed address on the friends list
    ads: bool  # ads may show to this account (everyone but Plus)


class AdIds(Strict):
    client: str  # ca-pub-...
    slot: str


class PlusPerks(Strict):
    coins: int  # each paid month
    items: dict[str, int]  # party items each paid month


class BillingConfig(Strict):
    payments: bool  # Plus is on sale (Paddle is set up)
    environment: str  # sandbox | production
    client_token: str  # Paddle.js client-side token ("" when off)
    plus_price: str  # Paddle price id for Plus ("" when off)
    ads: AdIds | None  # AdSense ids (None: no ads on this site)
    perks: PlusPerks


class PlusCheckout(Strict):
    price: str
    custom_data: dict[str, str]  # your account, signed by the server (Paddle hands it back)
    email: str | None  # prefilled at checkout when confirmed


class LookOption(Strict):
    id: str
    name: str
    level: int  # the level that unlocks it (0: Plus or the shop)
    plus: bool  # Plus members only
    price: int  # coins in the shop (0: not sold)
    unlocked: bool


class MyLook(Strict):
    """Your level unlocks: power-up slots, avatar frames and victory animations, and your picks."""

    level: int
    plus: bool
    slots: int  # power-ups you can use in one casual game
    slot_level: int  # the level that opens a second slot
    frame: str
    char: str
    win: str
    frames: list[LookOption]
    chars: list[LookOption]
    wins: list[LookOption]


class MyPlus(Strict):
    active: bool
    until: str | None  # ISO 8601
    status: str | None  # Paddle's: active | canceled | past_due | paused ...
    can_manage: bool  # a link to Paddle's page to change or cancel is available
    gift: bool  # Plus as a friend of the site (nothing to renew or cancel)
    source: str | None  # where the latest subscription was bought: paddle | app_store | play_store


class AppUser(Strict):
    app_user_id: str  # what the store app passes to RevenueCat (this account, signed)


class PlusManage(Strict):
    url: str


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
    google: bool  # sign in with Google is set up on this site
    staff: bool  # you're platform staff (the console also needs your authenticator app)


class GoogleLink(Strict):
    email: str | None


class Identities(Strict):
    google: GoogleLink | None  # linked Google account, if any
    google_available: bool
    has_password: bool


class RatingSeason(Strict):
    number: int
    starts: str  # ISO date
    ends: str


class MyRating(Strict):
    game: str
    title: str
    rating: int
    games: int
    tier: str  # "Provisional" until the placement games are played
    placement_left: int


class MyRatings(Strict):
    season: RatingSeason
    games: list[MyRating]
    place_boards: bool  # you appear on the leaderboards of places you're verified at
    rewards: list[SeasonReward]  # season rewards paid just now (shown once)


class BoardRow(Strict):
    username: str
    rating: int
    tier: str
    games: int
    gain: int | None  # this week's change (weekly boards only)
    you: bool


class LegendRow(Strict):
    username: str
    rating: int  # their best this season
    tier: str
    game: str  # the game it's in
    title: str
    you: bool


class ClubScoreRow(Strict):
    username: str
    score: int
    games: int  # club games that counted
    you: bool


class ClubBoards(Strict):
    season: RatingSeason
    legends: list[LegendRow]  # top 50: each member's best rating this season
    scores: list[ClubScoreRow]  # top 50: activity this season (club games, hosting, battles)


class RatingBoard(Strict):
    game: str
    title: str
    scope: str  # everyone | club | place
    period: str  # season | week
    season: RatingSeason
    rows: list[BoardRow]


class CoinEntry(Strict):
    delta: int
    reason: str  # opening | place | shop | season
    ref: str | None  # shop: the power-up; season: the game
    season: int | None  # season rewards: which season
    game: str | None  # place: the game finished
    place: int | None
    at: str  # ISO 8601


class CoinHistory(Strict):
    balance: int
    earned_today: int  # by playing, in the last 24 hours (what the daily cap counts)
    daily_cap: int
    entries: list[CoinEntry]  # newest first


class SeasonReward(Strict):
    game: str
    season: int
    tier: str
    coins: int


class BattleRow(Strict):
    game: str
    title: str
    kind: str  # duel | group
    place: int
    players: int
    prize: int
    note: str  # why no prize: limit | pair | device | left
    against: list[str]
    at: str


class HeadToHead(Strict):
    username: str
    won: int
    lost: int
    drawn: int


class Challenge(Strict):
    game: str
    title: str
    by: str  # who challenged you
    room: str
    open: bool  # the room is still there
    at: str


class BattleRecord(Strict):
    played: int
    trophies: int  # battles won
    prizes: int  # coins won in battles
    head_to_head: list[HeadToHead]
    recent: list[BattleRow]
    challenges: list[Challenge]  # duels waiting for you
    format: BattleFormat  # this week's featured format


class Quest(Strict):
    id: str
    title: str
    kind: str  # social | games | skill | club | fun
    social: bool  # means playing with someone new
    progress: int
    target: int
    claimed: bool


class QuestReward(Strict):
    xp: int
    coins: int


class Progress(Strict):
    level: int
    xp: int
    level_xp: int  # the XP this level started at
    next_xp: int  # the XP the next level starts at
    today_xp: int  # from games today (the daily cap counts these)
    daily_cap: int
    quests: list[Quest]  # today's three
    reward: QuestReward  # for each finished quest
    reroll_left: bool  # one swap a day
    streak: int  # days in a row with all three claimed
    streak_every: int  # a bonus every this many days
    weekly: WeeklyChallenges
    season: SeasonChallenges


class WeeklyChallenges(Strict):
    ends: str  # ISO date (Sunday)
    challenges: list[Quest]
    reward: QuestReward


class SeasonChallenges(Strict):
    season: int  # the ratings season's number
    ends: str  # ISO date (the season's last day)
    challenges: list[Quest]
    reward: QuestReward
    badges: list[int]  # seasons whose challenges you finished, all five


class BattleFormat(Strict):
    id: str
    title: str
    features: str  # what it features, in words ("Chess duels")
    games: list[str]  # game ids (empty = any game)
    kinds: list[str]  # duel | group
    bonus: float  # winners get this many times the usual prize


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
    status: Literal["offline", "online", "in_game", "up"]


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
    game: str  # the game it's used in


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
    place: str | None  # only people verified at this place (its slug) can join


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
    status: Literal["offline", "online", "in_game", "up"]
    up_game: str | None  # when up: the game they want (None: any)
    places: list[str]  # places they're verified at right now (badges)


class UpSignal(Strict):
    game: str | None
    until: str  # ISO 8601


class MatchInfo(Strict):
    """Enough people are up: a room is waiting (or waiting for its first player to open it)."""

    game: str | None
    players: int
    room: str | None
    mine: bool  # you're one of them


class ClubUp(Strict):
    mine: UpSignal | None
    count: int  # members up right now
    needed: int  # how many make a match
    match: MatchInfo | None


class ClubRoom(Strict):
    """A live room of the club, for members to walk into."""

    code: str
    host: str
    players: int
    phase: str
    game: str | None
    open: bool  # still in the lobby and not locked
    battle: bool  # a battle waiting to be played


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


class ClubChallenge(Strict):
    id: str
    title: str
    progress: int  # the club's, capped at the target
    target: int
    ends: str  # the last day (ISO date, UTC)
    helped: bool  # you've played a club game this week (needed to claim)
    claimed: bool
    reward: QuestReward


class HappeningRoom(ClubRoom):
    club: str  # the club's name
    slug: str


class Happening(Strict):
    """What's on for you right now: live rooms in your clubs and battle challenges waiting."""

    rooms: list[HappeningRoom]  # open lobbies first, then the fullest
    challenges: int  # battle challenges waiting for your answer


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
    up: ClubUp
    muted: bool  # you turned off "a club game is filling up" for this club
    open_reports: int  # reports waiting for the moderators (0 unless you're one)
    place: PlaceRef | None  # the place the club is for, when it requires one
    secure_nudge: bool  # you run this club without the authenticator app: suggest turning it on
    challenge: ClubChallenge | None  # this week's shared goal (None while accounts are down)


class InboxItem(Strict):
    id: int
    kind: str
    title: str
    body: str
    link: str  # a path on this site
    at: str  # ISO 8601
    read: bool


class Inbox(Strict):
    items: list[InboxItem]
    unread: int
    push_key: str  # the VAPID public key for pushManager.subscribe()


class KindInfo(Strict):
    id: str
    label: str
    on: bool


class NotifyPrefs(Strict):
    hidden: bool  # appear offline
    quiet: QuietHours | None
    kinds: list[KindInfo]
    devices: int  # browsers subscribed to pushes


class BlockedPerson(Strict):
    username: str
    since: str  # ISO 8601


class BlockList(Strict):
    people: list[BlockedPerson]


class ChatLine(Strict):
    name: str
    text: str


class TriageInfo(Strict):
    label: str
    score: float | None  # 0..1, when a model gave one
    summary: str
    by: str  # who triaged it ("ai-triage", "jira"...)


class TicketLink(Strict):
    system: str
    key: str
    url: str | None


class HistoryRow(Strict):
    at: str
    actor: str
    text: str


class ReportRow(Strict):
    id: int
    target: str  # the name they went by
    member: bool  # still in the club
    reason: str
    note: str
    context: list[ChatLine]  # their last chat lines in the room, taken by the server
    room: str | None
    status: Literal["open", "triaged", "escalated", "dismissed", "actioned"]
    at: str
    can_act: bool  # you may mute, remove or ban them (they're below your role)
    # The case around the report (events.py)
    public_id: str  # "rpt_...": the id other systems and support use
    priority: Literal["low", "normal", "high", "urgent"]
    triage: TriageInfo | None  # a person's or a model's first read
    tickets: list[TicketLink]  # the same case in other systems (Jira...)
    history: list[HistoryRow]  # its timeline, oldest first


class MutedRow(Strict):
    username: str
    until: str


class ActionRow(Strict):
    actor: str
    target: str
    action: str
    note: str
    at: str


class ClubReports(Strict):
    reports: list[ReportRow]
    muted: list[MutedRow]
    actions: list[ActionRow]  # the audit log, newest first
    reasons: dict[str, str]  # id -> label, for the report form


class StaffReportRow(Strict):
    id: int
    target: str  # the name they went by
    account: str | None  # their account, when they had one
    reason: str
    note: str
    context: list[ChatLine]
    room: str | None
    club: str | None  # the club it came from, if any
    status: Literal["open", "triaged", "escalated", "dismissed", "actioned"]
    at: str
    can_suspend: bool
    can_return: bool  # an escalated club case can go back to its club
    public_id: str
    priority: Literal["low", "normal", "high", "urgent"]
    triage: TriageInfo | None
    tickets: list[TicketLink]
    history: list[HistoryRow]


class SuspendedRow(Strict):
    username: str
    until: str | None  # None: for good
    reason: str


class StaffQueue(Strict):
    reports: list[StaffReportRow]
    suspended: list[SuspendedRow]
    actions: list[ActionRow]  # the staff audit log, newest first


class IntegrationReports(Strict):
    reports: list[dict[str, Any]]  # events.report_payload, version 1


class IntegrationReport(Strict):
    report: dict[str, Any]
    timeline: list[dict[str, Any]]


class IntegrationHealth(Strict):
    pending: int
    failed: int
    sinks: list[str]


class MyPlace(Strict):
    slug: str
    name: str
    kind: Literal["college", "company"]
    status: Literal["verified", "alumni"]  # alumni: the year ran out; verify again to renew
    verified_at: str
    expires_at: str


class MyPlaces(Strict):
    places: list[MyPlace]
    mail: bool  # verifying needs email to be set up on the site


class PlaceRef(Strict):
    slug: str
    name: str


class PlaceSummary(Strict):
    slug: str
    name: str
    kind: Literal["college", "company"]


class PlaceList(Strict):
    places: list[PlaceSummary]


class PlaceStarted(Strict):
    place: PlaceRef
    sent_to: str  # the address, masked: "a***@iitd.ac.in"


class StaffPlace(Strict):
    slug: str
    name: str
    kind: Literal["college", "company"]
    domains: list[str]
    members: int  # verified now


class PlaceRequestRow(Strict):
    domain: str
    count: int
    last_at: str


class StaffPlaces(Strict):
    places: list[StaffPlace]
    requests: list[PlaceRequestRow]


class SessionRow(Strict):
    id: str  # the start of the session's hash: names it, can't sign anyone in
    device: str  # "Chrome on Windows"
    signed_in: str | None
    last_seen: str | None
    current: bool  # this browser


class SessionList(Strict):
    sessions: list[SessionRow]


class SiteInfo(Strict):
    privacy_contact: str | None
    operator: str | None  # the legal name that runs the site


class Invitee(Strict):
    username: str
    status: Literal["offline", "online", "in_game", "up"]
    why: Literal["friend", "club"]


class Invitees(Strict):
    people: list[Invitee]


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
class PodiumSpot(Strict):
    id: str  # player id
    points: int


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
    plus: bool  # a Snazzlebop Plus member: the badge by their name


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
    note: str = ""  # why coins were held back (fairplay.NOTES): limit | repeat | device | quick | solo
    xp: int = 0  # XP from this game (fair games only, progress.py)


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


class RatingNews(Strict):
    """One player's rating change after a ranked game (or counted false: the game didn't count)."""

    counted: bool
    before: int | None = None
    after: int | None = None
    games: int | None = None
    tier: str | None = None


class Ranked(Strict):
    on: bool  # this game is (or is about to be) rated
    news: dict[str, RatingNews]  # results: player id -> change
    ready: bool  # everyone online is signed in with their own account


class PartyEffect(Strict):
    id: int  # rises with each one: a screen plays the ones it hasn't yet
    item: str
    by: str  # the player's name in this room
    moment: Highlight | None  # the slow-mo replay's big moment (other items: None)


class Party(Strict):
    effects: list[PartyEffect]


class PowerItem(Strict):
    id: str
    name: str
    icon: str
    text: str


class PowerUse(Strict):
    pid: str
    item: str
    name: str
    icon: str


class Powers(Strict):
    offer: list[PowerItem]  # this game's power-ups you could use now (casual rooms, signed in)
    used: bool  # no power-up slots left this game
    left: int  # power-ups you can still use this game
    slots: int  # your slots per game (1, or 2 from level 10 or with Plus)
    news: list[PowerUse]  # who used what (everyone sees)
    mine: str | None  # what your power-up showed you alone


class BattlePrize(Strict):
    place: int
    prize: int
    note: str  # why no prize: limit | pair | device | left ("" when paid)


class BattleView(Strict):
    game: str | None  # the battle waiting to be played here (None: none)
    kind: str | None  # duel | group
    featured: bool  # in the week's featured format: the winners get more
    news: dict[str, BattlePrize]  # results: player id -> prize


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
    podium: list[PodiumSpot]  # results: this game's top three, best first
    quip: str
    reactions: list[Reaction]
    chat: Chat
    call: Call
    faces: dict[str, list[int]]
    looks: dict[str, dict[str, str]]  # pid -> their unlocked frame, character and victory animation
    night: Night
    entrance: Entrance | None
    crowd: Crowd
    market: Market | None
    cards: Cards | None
    rivals: Rivals
    season: Season | None
    intro: Intro | None
    teams: Teams | None
    ranked: Ranked
    battle: BattleView
    powers: Powers
    party: Party
    ready: Ready
    last_standings: list[Standing]
    scare: int
    players: list[PlayerRow]
    games: list[GameCard]
    categories: list[CategoryInfo]
    game: dict[str, Any] | None  # the game's own view (typed per game later)
    stage: str | None
    how_to: list[str]
