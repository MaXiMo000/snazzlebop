"""The HTTP API's response contract. Each route declares one of these as its response model, so the
OpenAPI document (exported to frontend/openapi.json) describes every body, and the web and mobile apps
generate their types from it instead of copying them by hand. Models forbid unknown fields:
tests/test_contract.py validates real responses against them, so a field added in a route but not
here fails the build.

Request bodies stay next to their routes (main.py, accounts.py)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


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
    username: str
    coins: int
    powerups: dict[str, int]


class UserBody(Strict):
    user: PublicUser


class NewAccount(Strict):
    """Sign-up and recovery: the recovery code is shown once and never again."""

    user: PublicUser
    recovery_code: str


class Me(Strict):
    user: PublicUser | None
    accounts: bool  # false when the server has no database: sign-in is unavailable


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


ERRORS: dict[int | str, dict[str, object]] = {
    status: {"model": ErrorBody} for status in (400, 401, 403, 404, 409, 422, 429, 503)
}
