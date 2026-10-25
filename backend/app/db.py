"""Optional persistence: anonymous per-game results, generated content, and snapshots of live rooms
(so a restart or a deploy doesn't end a game). Game results hold no names, IPs or tokens; a room
snapshot holds what the room holds (display names, scores) and is deleted when the room ends.

The game never depends on the database: every call here fails soft.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import (
    JSON,
    Connection,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    case,
    delete,
    func,
    inspect,
    or_,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from . import ratings as ratinglib

log = logging.getLogger("snazzlebop.db")
INBOX_KEEP = 100  # inbox entries kept per person

MIGRATIONS = Path(__file__).with_name("migrations")
BASELINE = "0001"  # the schema as it stood before migrations: older databases are stamped with it


class Base(DeclarativeBase):
    pass


class GameResult(Base):
    __tablename__ = "game_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(String(32), index=True)
    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ContentItem(Base):
    """Generated game content (prompts, items, clues...). Never anything about players."""

    __tablename__ = "content_items"
    __table_args__ = (UniqueConstraint("kind", "key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    key: Mapped[str] = mapped_column(String(200))
    payload: Mapped[Any] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class RoomSnapshot(Base):
    """A live room, so it survives a restart or a deploy (rooms.Hub saves it after every change).
    Holds what the room holds (names, scores, the game in progress) and is deleted when the room ends."""

    __tablename__ = "room_snapshots"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class User(Base):
    """An account: username + scrypt hash, a keyed hash of the recovery code, coins, power-ups owned."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(20))
    username_key: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # casefolded
    pw_hash: Mapped[str] = mapped_column(String(200))
    recovery_hash: Mapped[str] = mapped_column(String(64))
    coins: Mapped[int] = mapped_column(Integer, default=0)
    powerups: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    # Optional, lower-cased. Only a confirmed address is used: for signing in, reset links and notices.
    email: Mapped[str | None] = mapped_column(String(254), nullable=True, index=True)
    email_verified: Mapped[bool] = mapped_column(default=False)
    # A platform suspension by staff (staff.py): no sign-in until then. Far in the future = permanent.
    suspended_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspend_reason: Mapped[str] = mapped_column(String(200), default="")
    # Shown on the leaderboards of places this account is verified at (off unless switched on).
    place_boards: Mapped[bool] = mapped_column(default=False)


class EmailToken(Base):
    """A link we emailed (confirm an address, reset a password). Only its SHA-256 is kept; used once."""

    __tablename__ = "email_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(8))  # "verify" | "reset"
    email: Mapped[str] = mapped_column(String(254))  # the address it was sent to
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Notification(Base):
    """One inbox entry (notify.py). `scope` is what daily limits count ("club_up:12"); `group_key` lets
    a newer one replace an unread one about the same thing."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    scope: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(String(240))
    link: Mapped[str] = mapped_column(String(200))
    group_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    pushed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PushSub(Base):
    """A browser that agreed to get pushes: its push-service endpoint and the keys to encrypt to."""

    __tablename__ = "push_subs"

    endpoint: Mapped[str] = mapped_column(String(1000), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    p256dh: Mapped[str] = mapped_column(String(120))
    auth: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class UserPrefs(Base):
    """Notification and presence settings (notify.clean_prefs keeps them well-formed)."""

    __tablename__ = "user_prefs"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Block(Base):
    """One account blocking another. Silent: the blocked person is never told."""

    __tablename__ = "blocks"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    blocked_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Report(Base):
    """A report about a person. `context` is captured by the server (their recent chat lines in the
    room), never taken from the reporter. Club reports go to the club's moderators; the rest, and
    escalated ones, to platform staff."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reporter_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    target_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_name: Mapped[str] = mapped_column(String(40))  # as shown at the time (guests have no account)
    club_id: Mapped[int | None] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    room_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    reason: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(String(500))
    context: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(12), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    handled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # A report is a case other systems can work on too (events.py): a stable public id, a priority,
    # who's on it, links to tickets elsewhere ({"jira": {"key": ..., "url": ...}}), and triage notes
    # from a person or a model ({"label", "score", "summary", "by"}).
    public_id: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    priority: Mapped[str] = mapped_column(String(8), default="normal")
    assignee: Mapped[str | None] = mapped_column(String(80), nullable=True)
    external: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    triage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Platform staff own this case: it was escalated, or it isn't about a club at all.
    staff: Mapped[bool] = mapped_column(default=False, index=True)


class ReportEvent(Base):
    """A report's timeline: everything that happened to it, by whom ("user:Cy", "integration:jira",
    "system"), kept even after the people involved leave."""

    __tablename__ = "report_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(80))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class OutboxItem(Base):
    """An event waiting to be delivered to one destination (outbox.py). Written in the same transaction
    as the change it describes, so a crash can't lose it; delivered at least once, with retries."""

    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sink: Mapped[str] = mapped_column(String(24))
    topic: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(String(200), default="")


class ModAction(Base):
    """The audit log: every moderator action, kept even when the people involved leave."""

    __tablename__ = "mod_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    club_id: Mapped[int | None] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(40))
    target_name: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Place(Base):
    """A college or company people can prove they belong to (places.py)."""

    __tablename__ = "places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(10))  # "college" | "company"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PlaceDomain(Base):
    """An email domain that proves membership of a place ("iitd.ac.in"; subdomains count too)."""

    __tablename__ = "place_domains"

    domain: Mapped[str] = mapped_column(String(120), primary_key=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), index=True)


class UserPlace(Base):
    """An account verified at a place. Lapses after a year (then shown as alumni) until verified again.
    `email_hash` is a keyed hash of the address used, never the address: one address, one account."""

    __tablename__ = "user_places"
    __table_args__ = (UniqueConstraint("place_id", "email_hash"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), primary_key=True)
    email_hash: Mapped[str] = mapped_column(String(64))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlaceCode(Base):
    """A pending verification: the code emailed to a college or work address (hashed), a few tries."""

    __tablename__ = "place_codes"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"))
    email_hash: Mapped[str] = mapped_column(String(64))
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlaceRequest(Base):
    """A domain people tried that no place has yet: staff decide whether to add it."""

    __tablename__ = "place_requests"

    domain: Mapped[str] = mapped_column(String(120), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
    last_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | added | declined


class KnownDevice(Base):
    """Browsers an account has signed in from (a hash of a random cookie), to email about new ones."""

    __tablename__ = "known_devices"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    device_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Session(Base):
    """A signed-in browser. Only the SHA-256 of the cookie's token is kept."""

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # For the account page's device list: what it is ("Chrome on Windows"), when it signed in and
    # when it was last used (updated at most every few minutes).
    device: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Result(Base):
    """One account's finish in one game: stats, seasons and coin history."""

    __tablename__ = "results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    game_id: Mapped[str] = mapped_column(String(32))
    season: Mapped[str] = mapped_column(String(7), index=True)  # "2026-10"
    place: Mapped[int] = mapped_column(Integer)
    players: Mapped[int] = mapped_column(Integer)
    points: Mapped[int] = mapped_column(Integer)
    coins: Mapped[int] = mapped_column(Integer)
    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class SkillRating(Base):
    """One account's rating in one ranked game (ratings.py). `season` is when it was last played: a
    later season pulls it halfway back to the start before it's used or shown."""

    __tablename__ = "ratings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    game_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    mu: Mapped[float] = mapped_column(Float)
    sigma: Mapped[float] = mapped_column(Float)
    games: Mapped[int] = mapped_column(Integer, default=0)
    season: Mapped[int] = mapped_column(Integer, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class RatingEvent(Base):
    """One rating change from one ranked game: the history, the day cap and the same-pair limit."""

    __tablename__ = "rating_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match: Mapped[str] = mapped_column(String(24), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    game_id: Mapped[str] = mapped_column(String(32))
    season: Mapped[int] = mapped_column(Integer)
    place: Mapped[int] = mapped_column(Integer)
    before: Mapped[int] = mapped_column(Integer)
    after: Mapped[int] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class LedgerEntry(Base):
    """One change to an account's coins: append-only, never edited. users.coins is the cached sum,
    updated in the same transaction. (reason, ref) names what caused it, once: posting the same one
    twice is refused, so retries can't pay twice."""

    __tablename__ = "ledger"
    __table_args__ = (UniqueConstraint("user_id", "reason", "ref_type", "ref_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    currency: Mapped[str] = mapped_column(String(8), default="coins")
    delta: Mapped[int] = mapped_column(Integer)
    # opening (the balance before the ledger) | place (a finished game) | shop | season (rating reward)
    reason: Mapped[str] = mapped_column(String(24))
    ref_type: Mapped[str] = mapped_column(String(16))  # result | item | rating | account
    ref_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class Friend(Base):
    """One account added another. Friends see each other's rooms only once both have added the other."""

    __tablename__ = "friends"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    friend_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class Circle(Base):
    """What a host's rooms remember from one night to the next: who holds the champion's belt (a display
    name) and the forfeits their group wrote for the loser's wheel."""

    __tablename__ = "circles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    belt: Mapped[str] = mapped_column(String(32), default="")
    forfeits: Mapped[list[str]] = mapped_column(JSON, default=list)


class Identity(Base):
    """A way to sign in other than the password: today Google, by its stable account id ("sub").
    An account may have several; one without a password must keep at least one."""

    __tablename__ = "identities"

    provider: Mapped[str] = mapped_column(String(16), primary_key=True)
    subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(254), default="")  # as the provider reported it, verified
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Mfa(Base):
    """An account's authenticator-app sign-in (app.mfa): the salt its secret is derived from (the secret
    itself is never stored), whether it is switched on yet, the last time step accepted (so a code can't
    be replayed), and the keyed hashes of its unused backup codes."""

    __tablename__ = "mfa"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    salt: Mapped[str] = mapped_column(String(32))
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_step: Mapped[int] = mapped_column(Integer, default=0)
    backup_hashes: Mapped[list[str]] = mapped_column(JSON, default=list)


class Club(Base):
    """A community: people from one place or one group who play together. Joined by invite for now."""

    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(40))
    about: Mapped[str] = mapped_column(String(200), default="")
    rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # see app.clubs.policy.clean_rules
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Membership(Base):
    """One account in one club: its role there (owner, admin, moderator, member) and whether it's banned."""

    __tablename__ = "memberships"

    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(String(12), default="member")
    banned: Mapped[bool] = mapped_column(default=False)
    # A moderator's mute: no chat in the club's rooms until then.
    muted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ClubInvite(Base):
    """An invite link. Only the code's keyed hash is kept; it expires and runs out of uses."""

    __tablename__ = "club_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    uses_left: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


MAX_FRIENDS = 50


def make_engine(url: str) -> AsyncEngine:
    if url.startswith("sqlite"):
        kwargs: dict[str, Any] = {}
        if ":memory:" in url:
            kwargs.update(poolclass=StaticPool, connect_args={"check_same_thread": False})
        return create_async_engine(url, **kwargs)
    return create_async_engine(url, pool_size=5, max_overflow=5, pool_recycle=1800, pool_pre_ping=True)


def migrate(conn: Connection) -> None:
    """Bring the schema up to the newest migration. A database made before migrations existed (it has
    the tables but no revision) is stamped as the baseline first, so nothing is created twice."""
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.attributes["connection"] = conn
    if MigrationContext.configure(conn).get_current_revision() is None and inspect(conn).has_table("users"):
        command.stamp(cfg, BASELINE)
    command.upgrade(cfg, "head")


class Database:
    def __init__(self, url: str) -> None:
        self.engine = make_engine(url)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.ready = False

    async def init(self) -> None:
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(migrate)
            self.ready = True
        except Exception:
            log.exception("database unavailable; continuing without persistence")

    async def record(self, game_id: str, summary: dict[str, Any]) -> None:
        if not self.ready:
            return
        try:
            async with self.sessions() as session:
                session.add(GameResult(game_id=game_id, summary=summary))
                await session.commit()
        except Exception:
            log.exception("could not record game result")

    async def stats(self) -> dict[str, int]:
        if not self.ready:
            return {}
        try:
            async with self.sessions() as session:
                rows = await session.execute(
                    select(GameResult.game_id, func.count()).group_by(GameResult.game_id)
                )
                return {game: int(n) for game, n in rows.all()}
        except Exception:
            log.exception("could not read stats")
            return {}

    async def save_content(self, kind: str, items: list[tuple[str, Any]]) -> None:
        if not self.ready:
            return
        for key, payload in items:  # one by one: a duplicate (unique kind+key) only skips itself
            try:
                async with self.sessions() as session:
                    session.add(ContentItem(kind=kind, key=key[:200], payload=payload))
                    await session.commit()
            except Exception:
                log.info("content item skipped (duplicate or db error)")

    async def load_content(self) -> list[tuple[str, Any]]:
        if not self.ready:
            return []
        try:
            async with self.sessions() as session:
                rows = await session.execute(
                    select(ContentItem.kind, ContentItem.payload).order_by(ContentItem.id)
                )
                return [(k, p) for k, p in rows.all()]
        except Exception:
            log.exception("could not load generated content")
            return []

    # -- room snapshots ---------------------------------------------------------------------------
    async def save_snapshot(self, code: str, data: bytes) -> None:
        if not self.ready:
            return
        try:
            async with self.sessions() as session:
                await session.merge(RoomSnapshot(code=code, data=data, updated_at=datetime.now(UTC)))
                await session.commit()
        except Exception:
            log.exception("could not save a room snapshot")

    async def load_snapshot(self, code: str) -> bytes | None:
        if not self.ready:
            return None
        try:
            async with self.sessions() as session:
                row = await session.get(RoomSnapshot, code)
                return bytes(row.data) if row is not None else None
        except Exception:
            log.exception("could not load a room snapshot")
            return None

    async def delete_snapshots(self, codes: list[str]) -> None:
        if not self.ready or not codes:
            return
        try:
            async with self.sessions() as session:
                await session.execute(delete(RoomSnapshot).where(RoomSnapshot.code.in_(codes)))
                await session.commit()
        except Exception:
            log.exception("could not delete room snapshots")

    async def purge_snapshots(self, older_than_seconds: float) -> None:
        """Rooms nobody came back to (the server was down longer than a room lives)."""
        if not self.ready:
            return
        cutoff = datetime.now(UTC) - timedelta(seconds=older_than_seconds)
        try:
            async with self.sessions() as session:
                await session.execute(delete(RoomSnapshot).where(RoomSnapshot.updated_at < cutoff))
                await session.commit()
        except Exception:
            log.exception("could not purge old room snapshots")

    # -- accounts -------------------------------------------------------------------------------------
    # These raise on database errors (the HTTP layer turns that into a plain 500): unlike stats, an
    # account action that silently didn't happen would be a bug the player can see.
    async def create_user(self, username: str, pw_hash: str, recovery_hash: str) -> User | None:
        """The new account, or None if the username (any capitalisation) is taken."""
        try:
            async with self.sessions() as session:
                user = User(
                    username=username,
                    username_key=username.casefold(),
                    pw_hash=pw_hash,
                    recovery_hash=recovery_hash,
                    coins=0,
                    powerups={},
                )
                session.add(user)
                await session.commit()
                return user
        except IntegrityError:
            return None

    async def user_by_name(self, username: str) -> User | None:
        async with self.sessions() as session:
            row = await session.execute(select(User).where(User.username_key == username.casefold()))
            return row.scalar_one_or_none()

    async def user_for_session(self, token_hash: str) -> User | None:
        try:
            async with self.sessions() as session:
                row = await session.execute(
                    select(User, Session.expires_at, Session.last_seen)
                    .join(Session, Session.user_id == User.id)
                    .where(Session.token_hash == token_hash)
                )
                found = row.first()
                if found is None:
                    return None
                user, expires, seen = found
                now = datetime.now(UTC)
                if seen is None or now - aware(seen) > timedelta(minutes=5):
                    await session.execute(
                        update(Session).where(Session.token_hash == token_hash).values(last_seen=now)
                    )
                    await session.commit()
                if suspended(user):
                    return None
                if aware(expires) < datetime.now(UTC):
                    await session.execute(delete(Session).where(Session.token_hash == token_hash))
                    await session.commit()
                    return None
                return user
        except Exception:
            log.exception("could not read a session")
            return None

    async def create_session(
        self, token_hash: str, user_id: int, ttl_seconds: float, device: str = ""
    ) -> None:
        async with self.sessions() as session:
            now = datetime.now(UTC)
            expires = now + timedelta(seconds=ttl_seconds)
            session.add(
                Session(
                    token_hash=token_hash,
                    user_id=user_id,
                    expires_at=expires,
                    device=device[:60],
                    created_at=now,
                    last_seen=now,
                )
            )
            await session.execute(delete(Session).where(Session.expires_at < datetime.now(UTC)))
            await session.commit()

    async def session_started(self, token_hash: str) -> datetime | None:
        """When this session signed in (to let a password-less account confirm a sensitive change)."""
        async with self.sessions() as session:
            at = await session.scalar(select(Session.created_at).where(Session.token_hash == token_hash))
            return aware(at) if at is not None else None

    # -- other ways to sign in (oidc.py) ---------------------------------------------------------------
    async def identity_user(self, provider: str, subject: str) -> User | None:
        async with self.sessions() as session:
            row = await session.get(Identity, (provider, subject))
            return await session.get(User, row.user_id) if row is not None else None

    async def identities(self, user_id: int) -> list[Identity]:
        async with self.sessions() as session:
            rows = await session.execute(select(Identity).where(Identity.user_id == user_id))
            return list(rows.scalars().all())

    async def add_identity(self, user_id: int, provider: str, subject: str, email: str) -> bool:
        """Link a sign-in to the account; False if it already belongs to another account."""
        async with self.sessions() as session:
            row = await session.get(Identity, (provider, subject))
            if row is not None:
                return row.user_id == user_id
            mine = await session.scalar(
                select(Identity).where(Identity.user_id == user_id, Identity.provider == provider)
            )
            if mine is not None:  # one account per provider: replace the old link
                await session.delete(mine)
            session.add(Identity(provider=provider, subject=subject, user_id=user_id, email=email[:254]))
            await session.commit()
            return True

    async def remove_identity(self, user_id: int, provider: str) -> None:
        async with self.sessions() as session:
            await session.execute(
                delete(Identity).where(Identity.user_id == user_id, Identity.provider == provider)
            )
            await session.commit()

    async def create_identity_user(
        self, username: str, recovery_hash: str, provider: str, subject: str, email: str | None
    ) -> User | None:
        """A new account that signs in only through a provider (no password yet). None if the
        username is taken."""
        try:
            async with self.sessions() as session:
                user = User(
                    username=username,
                    username_key=username.casefold(),
                    pw_hash="",
                    recovery_hash=recovery_hash,
                    coins=0,
                    powerups={},
                    email=email,
                    email_verified=email is not None,
                )
                session.add(user)
                await session.flush()
                session.add(Identity(provider=provider, subject=subject, user_id=user.id, email=email or ""))
                await session.commit()
                return user
        except IntegrityError:
            return None

    async def user_sessions(self, user_id: int) -> list[Session]:
        """The account's signed-in browsers, most recently used first."""
        now = datetime.now(UTC)
        async with self.sessions() as session:
            rows = await session.execute(
                select(Session).where(Session.user_id == user_id, Session.expires_at > now)
            )
            found = list(rows.scalars().all())
        return sorted(found, key=lambda s: aware(s.last_seen or s.created_at or now), reverse=True)

    async def delete_session_by_prefix(self, user_id: int, prefix: str) -> bool:
        """Sign out one of the account's browsers, named by the start of its hash (what the list shows)."""
        async with self.sessions() as session:
            rows = await session.execute(select(Session.token_hash).where(Session.user_id == user_id))
            match = [h for (h,) in rows.all() if h.startswith(prefix)]
            if len(match) != 1:
                return False
            await session.execute(delete(Session).where(Session.token_hash == match[0]))
            await session.commit()
            return True

    async def delete_session(self, token_hash: str) -> None:
        async with self.sessions() as session:
            await session.execute(delete(Session).where(Session.token_hash == token_hash))
            await session.commit()

    async def delete_sessions(self, user_id: int, keep: str | None = None) -> None:
        """Sign the account out everywhere (except the session whose hash is `keep`)."""
        async with self.sessions() as session:
            where = [Session.user_id == user_id] + ([Session.token_hash != keep] if keep else [])
            await session.execute(delete(Session).where(*where))
            await session.commit()

    async def user_by_id(self, user_id: int) -> User | None:
        async with self.sessions() as session:
            return await session.get(User, user_id)

    async def user_by_email(self, email: str) -> User | None:
        """The account this address is confirmed on (an unconfirmed address belongs to nobody)."""
        async with self.sessions() as session:
            row = await session.execute(
                select(User).where(User.email == email.lower(), User.email_verified.is_(True)).limit(1)
            )
            return row.scalar_one_or_none()

    async def set_email(self, user_id: int, email: str | None) -> None:
        """A new (unconfirmed) address, or None to remove it. Links sent to an old address stop working."""
        async with self.sessions() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(email=email.lower() if email else None, email_verified=False)
            )
            await session.execute(delete(EmailToken).where(EmailToken.user_id == user_id))
            await session.commit()

    async def add_token(
        self, token_hash: str, user_id: int, purpose: str, email: str, ttl_seconds: float
    ) -> None:
        """A new emailed link; it replaces any earlier one for the same purpose."""
        async with self.sessions() as session:
            now = datetime.now(UTC)
            await session.execute(
                delete(EmailToken).where(
                    or_(
                        (EmailToken.user_id == user_id) & (EmailToken.purpose == purpose),
                        EmailToken.expires_at < now,
                    )
                )
            )
            session.add(
                EmailToken(
                    token_hash=token_hash,
                    user_id=user_id,
                    purpose=purpose,
                    email=email.lower(),
                    expires_at=now + timedelta(seconds=ttl_seconds),
                )
            )
            await session.commit()

    async def take_token(self, token_hash: str, purpose: str) -> tuple[User, str] | None:
        """Spend an emailed link: (its account, the address it went to), or None if unknown or expired."""
        async with self.sessions() as session:
            row = await session.get(EmailToken, token_hash)
            if row is None or row.purpose != purpose:
                return None
            user_id, email, expires = row.user_id, row.email, row.expires_at
            # Only the request whose delete removed the row may use it: two clicks can't both spend it.
            done = await session.execute(delete(EmailToken).where(EmailToken.token_hash == token_hash))
            await session.commit()
            if not done.rowcount or aware(expires) < datetime.now(UTC):
                return None
            user = await session.get(User, user_id)
            return (user, email) if user is not None else None

    async def peek_token(self, token_hash: str, purpose: str) -> User | None:
        """The account a live emailed link is for, without spending it."""
        async with self.sessions() as session:
            row = await session.get(EmailToken, token_hash)
            if row is None or row.purpose != purpose or aware(row.expires_at) < datetime.now(UTC):
                return None
            return await session.get(User, row.user_id)

    async def confirm_email(self, user_id: int, email: str) -> bool:
        """Mark the address confirmed, if it's still the account's and no other account has confirmed it."""
        async with self.sessions() as session:
            taken = await session.scalar(
                select(func.count()).where(
                    User.email == email, User.email_verified.is_(True), User.id != user_id
                )
            )
            if taken:
                return False
            done = await session.execute(
                update(User).where(User.id == user_id, User.email == email).values(email_verified=True)
            )
            await session.commit()
            return bool(done.rowcount)

    async def note_device(self, user_id: int, device_hash: str) -> tuple[bool, bool]:
        """Remember a browser for the account: (seen before, the account had any devices before)."""
        async with self.sessions() as session:
            row = await session.get(KnownDevice, (user_id, device_hash))
            had = bool(await session.scalar(select(func.count()).where(KnownDevice.user_id == user_id)))
            if row is None:
                session.add(KnownDevice(user_id=user_id, device_hash=device_hash))
            else:
                row.last_seen = datetime.now(UTC)
            await session.commit()
            return row is not None, had

    async def set_credentials(self, user_id: int, pw_hash: str, recovery_hash: str | None) -> None:
        values: dict[str, Any] = {"pw_hash": pw_hash}
        if recovery_hash is not None:
            values["recovery_hash"] = recovery_hash
        async with self.sessions() as session:
            await session.execute(update(User).where(User.id == user_id).values(**values))
            await session.commit()

    async def delete_user(self, user_id: int) -> list[int]:
        """The account and everything tied to it: sessions, results, coins, power-ups."""
        async with self.sessions() as session:
            await session.execute(delete(Session).where(Session.user_id == user_id))
            await session.execute(delete(Result).where(Result.user_id == user_id))
            await session.execute(delete(Circle).where(Circle.user_id == user_id))
            await session.execute(delete(Mfa).where(Mfa.user_id == user_id))
            await session.execute(delete(EmailToken).where(EmailToken.user_id == user_id))
            await session.execute(delete(KnownDevice).where(KnownDevice.user_id == user_id))
            await session.execute(delete(Notification).where(Notification.user_id == user_id))
            await session.execute(delete(PushSub).where(PushSub.user_id == user_id))
            await session.execute(delete(UserPrefs).where(UserPrefs.user_id == user_id))
            await session.execute(delete(UserPlace).where(UserPlace.user_id == user_id))
            await session.execute(delete(Identity).where(Identity.user_id == user_id))
            await session.execute(delete(SkillRating).where(SkillRating.user_id == user_id))
            await session.execute(delete(LedgerEntry).where(LedgerEntry.user_id == user_id))
            await session.execute(delete(RatingEvent).where(RatingEvent.user_id == user_id))
            await session.execute(delete(PlaceCode).where(PlaceCode.user_id == user_id))
            await session.execute(
                delete(Block).where(or_(Block.user_id == user_id, Block.blocked_id == user_id))
            )
            closed = await self._pass_on_clubs(session, user_id)
            await session.execute(delete(Membership).where(Membership.user_id == user_id))
            await session.execute(
                delete(Friend).where(or_(Friend.user_id == user_id, Friend.friend_id == user_id))
            )
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
            return closed

    @staticmethod
    async def drop_club(session: Any, club_id: int) -> None:
        """A club and everything in it. Spelled out rather than left to ON DELETE CASCADE, which SQLite
        only honours when foreign keys are switched on."""
        await session.execute(
            delete(ReportEvent).where(
                ReportEvent.report_id.in_(select(Report.id).where(Report.club_id == club_id))
            )
        )
        for table in (ClubInvite, Membership, Report, ModAction):
            await session.execute(delete(table).where(table.club_id == club_id))
        await session.execute(delete(Club).where(Club.id == club_id))

    @staticmethod
    async def _pass_on_clubs(session: Any, user_id: int) -> list[int]:
        """Clubs an account owns go to the next in line (highest role, then longest in); a club with
        nobody else in it closes. Returns the clubs that closed."""
        closed: list[int] = []
        owned = await session.scalars(
            select(Membership.club_id).where(Membership.user_id == user_id, Membership.role == "owner")
        )
        rank = case({"admin": 0, "moderator": 1}, value=Membership.role, else_=2)
        for club_id in owned.all():
            heir = await session.scalar(
                select(Membership)
                .where(
                    Membership.club_id == club_id,
                    Membership.user_id != user_id,
                    Membership.banned.is_(False),
                )
                .order_by(rank, Membership.joined_at)
                .limit(1)
            )
            if heir is not None:
                heir.role = "owner"
            else:
                await Database.drop_club(session, club_id)
                closed.append(club_id)
        return closed

    # -- authenticator-app sign-in ------------------------------------------------------------------
    async def mfa(self, user_id: int) -> Mfa | None:
        async with self.sessions() as session:
            return await session.get(Mfa, user_id)

    async def start_mfa(self, user_id: int, salt: str) -> None:
        """A new (not yet confirmed) set-up; replaces an unconfirmed one, never a working one."""
        async with self.sessions() as session:
            row = await session.get(Mfa, user_id)
            if row is None:
                session.add(Mfa(user_id=user_id, salt=salt, last_step=0, backup_hashes=[]))
            elif row.enabled_at is None:
                row.salt, row.last_step, row.backup_hashes = salt, 0, []
            await session.commit()

    async def enable_mfa(self, user_id: int, backup_hashes: list[str]) -> None:
        async with self.sessions() as session:
            await session.execute(
                update(Mfa)
                .where(Mfa.user_id == user_id)
                .values(enabled_at=datetime.now(UTC), backup_hashes=backup_hashes)
            )
            await session.commit()

    async def use_step(self, user_id: int, step: int) -> bool:
        """Accept a code's time step once: False if this step (or a later one) was already used. A single
        conditional update, so two sign-ins racing with the same code can't both win."""
        async with self.sessions() as session:
            done = await session.execute(
                update(Mfa).where(Mfa.user_id == user_id, Mfa.last_step < step).values(last_step=step)
            )
            await session.commit()
            return bool(done.rowcount)

    async def spend_backup(self, user_id: int, take: Callable[[list[str]], list[str] | None]) -> bool:
        """Spend a backup code: `take` returns the hashes left, or None if the code isn't one. The row is
        locked while it's checked, so a code can't be spent twice at once."""
        async with self.sessions() as session:
            row = (
                await session.execute(select(Mfa).where(Mfa.user_id == user_id).with_for_update())
            ).scalar_one_or_none()
            left = take(list(row.backup_hashes or [])) if row is not None and row.enabled_at else None
            if left is None:
                return False
            row.backup_hashes = left
            await session.commit()
            return True

    async def set_backup_hashes(self, user_id: int, hashes: list[str]) -> None:
        async with self.sessions() as session:
            await session.execute(update(Mfa).where(Mfa.user_id == user_id).values(backup_hashes=hashes))
            await session.commit()

    async def delete_mfa(self, user_id: int) -> None:
        async with self.sessions() as session:
            await session.execute(delete(Mfa).where(Mfa.user_id == user_id))
            await session.commit()

    # -- blocks and reports (safety.py) ---------------------------------------------------------------
    async def block(self, user_id: int, other_id: int) -> None:
        """Block someone: any friendship between the two ends too."""
        async with self.sessions() as session:
            if await session.get(Block, (user_id, other_id)) is None:
                session.add(Block(user_id=user_id, blocked_id=other_id))
            await session.execute(
                delete(Friend).where(
                    or_(
                        (Friend.user_id == user_id) & (Friend.friend_id == other_id),
                        (Friend.user_id == other_id) & (Friend.friend_id == user_id),
                    )
                )
            )
            await session.commit()

    async def unblock(self, user_id: int, other_id: int) -> None:
        async with self.sessions() as session:
            await session.execute(delete(Block).where(Block.user_id == user_id, Block.blocked_id == other_id))
            await session.commit()

    async def blocked_by_me(self, user_id: int) -> list[tuple[str, datetime]]:
        async with self.sessions() as session:
            rows = await session.execute(
                select(User.username, Block.created_at)
                .join(Block, Block.blocked_id == User.id)
                .where(Block.user_id == user_id)
                .order_by(User.username_key)
            )
            return [(str(n), at) for n, at in rows.all()]

    async def block_set(self, user_id: int) -> set[int]:
        """Everyone this account must not meet: people it blocked and people who blocked it."""
        async with self.sessions() as session:
            mine = await session.scalars(select(Block.blocked_id).where(Block.user_id == user_id))
            theirs = await session.scalars(select(Block.user_id).where(Block.blocked_id == user_id))
            return set(mine.all()) | set(theirs.all())

    # Reports are cases: every change goes through _record, which writes the timeline entry and the
    # outbox events in the same transaction as the change. `payload(report, club)` builds the event body
    # (events.report_payload, passed in so this module stays free of it); `sinks` are the destinations.
    async def _record(
        self,
        session: Any,
        report: Report,
        kind: str,
        actor: str,
        data: dict[str, Any],
        topic: str,
        sinks: list[str],
        payload: Callable[[Report, Club | None], dict[str, Any]],
    ) -> None:
        now = datetime.now(UTC)
        report.updated_at = now
        await session.flush()
        session.add(ReportEvent(report_id=report.id, kind=kind, actor=actor[:80], data=data, created_at=now))
        if sinks:
            club = await session.get(Club, report.club_id) if report.club_id is not None else None
            body = {**payload(report, club), "event": {"kind": kind, "actor": actor, "data": data}}
            for sink in sinks:
                session.add(OutboxItem(sink=sink, topic=topic, payload=body, next_at=now))

    async def add_report(
        self,
        values: dict[str, Any],
        actor: str,
        sinks: list[str],
        payload: Callable[[Report, Club | None], dict[str, Any]],
    ) -> tuple[Report, bool]:
        """File a report. If this reporter already has an open one about the same person here, the new
        chat lines and note are added to it instead (one case to read, everything in it). Returns the
        report and whether it's new."""
        async with self.sessions() as session:
            same = await session.scalar(
                select(Report)
                .where(
                    Report.reporter_id == values["reporter_id"],
                    Report.status.in_(("open", "triaged")),
                    Report.club_id.is_(None)
                    if values.get("club_id") is None
                    else Report.club_id == values["club_id"],
                    (Report.target_id == values["target_id"])
                    if values.get("target_id") is not None
                    else (Report.target_name == values["target_name"])
                    & (Report.room_code == values.get("room_code")),
                )
                .limit(1)
            )
            if same is not None:
                old = list(same.context or [])
                added = [c for c in values.get("context", []) if c not in old]
                same.context = [*old, *added][-20:]
                note = values.get("note", "")
                if note and note not in same.note:
                    same.note = f"{same.note} / {note}".strip(" /")[:500]
                if values.get("room_code") and not same.room_code:
                    same.room_code = values["room_code"]
                data = {"note": note, "lines": len(added), "room": values.get("room_code")}
                await self._record(session, same, "merged", actor, data, "report.updated", sinks, payload)
                await session.commit()
                return same, False
            report = Report(**values, public_id=f"rpt_{secrets.token_urlsafe(9)}")
            session.add(report)
            data = {"reason": report.reason, "room": report.room_code}
            await self._record(session, report, "created", actor, data, "report.created", sinks, payload)
            await session.commit()
            return report, True

    async def update_report(
        self,
        report_id: int,
        changes: dict[str, Any],
        kind: str,
        actor: str,
        data: dict[str, Any],
        sinks: list[str],
        payload: Callable[[Report, Club | None], dict[str, Any]],
    ) -> Report | None:
        """Change a report (status, priority, assignee, handled_by...; `external` and `triage` are
        merged into what's there) and record it. None if the report is gone."""
        async with self.sessions() as session:
            report = await session.get(Report, report_id, with_for_update=True)
            if report is None:
                return None
            for key, value in changes.items():
                if key in ("external", "triage"):
                    setattr(report, key, {**(getattr(report, key) or {}), **value})
                else:
                    setattr(report, key, value)
            await self._record(session, report, kind, actor, data, "report.updated", sinks, payload)
            await session.commit()
            return report

    async def staff_reports(self) -> list[Report]:
        """Platform staff's queue: cases they own that are waiting first (by priority later, in the
        page), then the most recent ones they closed."""
        waiting = ("open", "triaged", "escalated")
        async with self.sessions() as session:
            rows = await session.execute(
                select(Report)
                .where(Report.staff.is_(True))
                .order_by(Report.status.in_(waiting).desc(), Report.created_at.desc())
                .limit(80)
            )
            return list(rows.scalars().all())

    async def suspend(self, user_id: int, until: datetime | None, reason: str) -> None:
        """Suspend (or, with None, lift a suspension): every session ends at once."""
        async with self.sessions() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(suspended_until=until, suspend_reason=reason[:200])
            )
            if until is not None:
                await session.execute(delete(Session).where(Session.user_id == user_id))
            await session.commit()

    async def suspended_users(self) -> list[User]:
        async with self.sessions() as session:
            rows = await session.execute(
                select(User).where(User.suspended_until.is_not(None)).order_by(User.suspended_until)
            )
            return [u for u in rows.scalars().all() if suspended(u)]

    async def staff_actions(self, limit: int = 40) -> list[ModAction]:
        async with self.sessions() as session:
            rows = await session.execute(
                select(ModAction)
                .where(ModAction.club_id.is_(None))
                .order_by(ModAction.created_at.desc(), ModAction.id.desc())
                .limit(limit)
            )
            return list(rows.scalars().all())

    async def reports_today(self, reporter_id: int) -> int:
        since = datetime.now(UTC) - timedelta(days=1)
        async with self.sessions() as session:
            n = await session.scalar(
                select(func.count()).where(Report.reporter_id == reporter_id, Report.created_at >= since)
            )
            return int(n or 0)

    async def club_reports(self, club_id: int) -> list[Report]:
        """Reports waiting for a decision first, then the most recent handled ones."""
        async with self.sessions() as session:
            rows = await session.execute(
                select(Report)
                .where(Report.club_id == club_id)
                .order_by(Report.status.in_(("open", "triaged")).desc(), Report.created_at.desc())
                .limit(60)
            )
            return list(rows.scalars().all())

    async def open_reports(self, club_id: int) -> int:
        async with self.sessions() as session:
            n = await session.scalar(
                select(func.count()).where(Report.club_id == club_id, Report.status.in_(("open", "triaged")))
            )
            return int(n or 0)

    async def report(self, report_id: int) -> Report | None:
        async with self.sessions() as session:
            return await session.get(Report, report_id)

    async def report_by_public_id(self, public_id: str) -> tuple[Report, Club | None] | None:
        async with self.sessions() as session:
            report = await session.scalar(select(Report).where(Report.public_id == public_id))
            if report is None:
                return None
            club = await session.get(Club, report.club_id) if report.club_id is not None else None
            return report, club

    async def reports_for_integration(
        self, statuses: tuple[str, ...], limit: int
    ) -> list[tuple[Report, Club | None]]:
        async with self.sessions() as session:
            rows = await session.execute(
                select(Report, Club)
                .outerjoin(Club, Club.id == Report.club_id)
                .where(Report.status.in_(statuses))
                .order_by(Report.created_at.desc())
                .limit(limit)
            )
            return [(r, c) for r, c in rows.all()]

    async def timelines(self, report_ids: list[int]) -> dict[int, list[ReportEvent]]:
        if not report_ids:
            return {}
        async with self.sessions() as session:
            rows = await session.execute(
                select(ReportEvent)
                .where(ReportEvent.report_id.in_(report_ids))
                .order_by(ReportEvent.created_at, ReportEvent.id)
            )
            out: dict[int, list[ReportEvent]] = {}
            for e in rows.scalars().all():
                out.setdefault(e.report_id, []).append(e)
            return out

    # -- the outbox (outbox.py) -------------------------------------------------------------------------
    async def outbox_due(self, limit: int) -> list[OutboxItem]:
        now = datetime.now(UTC)
        async with self.sessions() as session:
            rows = await session.execute(
                select(OutboxItem)
                .where(
                    OutboxItem.done_at.is_(None), OutboxItem.failed_at.is_(None), OutboxItem.next_at <= now
                )
                .order_by(OutboxItem.id)
                .limit(limit)
            )
            return list(rows.scalars().all())

    async def outbox_done(self, item_id: int) -> None:
        async with self.sessions() as session:
            await session.execute(
                update(OutboxItem).where(OutboxItem.id == item_id).values(done_at=datetime.now(UTC))
            )
            await session.commit()

    async def outbox_retry(self, item_id: int, attempts: int, next_at: datetime | None, error: str) -> None:
        """Try again at `next_at`, or give up (next_at None: it stays in the table, marked failed)."""
        values: dict[str, Any] = {"attempts": attempts, "last_error": error[:200]}
        if next_at is None:
            values["failed_at"] = datetime.now(UTC)
        else:
            values["next_at"] = next_at
        async with self.sessions() as session:
            await session.execute(update(OutboxItem).where(OutboxItem.id == item_id).values(**values))
            await session.commit()

    async def outbox_stats(self) -> dict[str, int]:
        async with self.sessions() as session:
            pending = await session.scalar(
                select(func.count()).where(OutboxItem.done_at.is_(None), OutboxItem.failed_at.is_(None))
            )
            failed = await session.scalar(select(func.count()).where(OutboxItem.failed_at.is_not(None)))
            return {"pending": int(pending or 0), "failed": int(failed or 0)}

    async def log_action(
        self, club_id: int | None, actor: Any, target_name: str, action: str, note: str
    ) -> None:
        async with self.sessions() as session:
            session.add(
                ModAction(
                    club_id=club_id,
                    actor_id=actor.id,
                    actor_name=actor.username,
                    target_name=target_name[:40],
                    action=action,
                    note=note[:200],
                )
            )
            await session.commit()

    async def club_actions(self, club_id: int, limit: int = 30) -> list[ModAction]:
        async with self.sessions() as session:
            rows = await session.execute(
                select(ModAction)
                .where(ModAction.club_id == club_id)
                .order_by(ModAction.created_at.desc(), ModAction.id.desc())
                .limit(limit)
            )
            return list(rows.scalars().all())

    async def mute_member(self, club_id: int, user_id: int, until: datetime | None) -> None:
        async with self.sessions() as session:
            await session.execute(
                update(Membership)
                .where(Membership.club_id == club_id, Membership.user_id == user_id)
                .values(muted_until=until)
            )
            await session.commit()

    async def club_mutes(self, club_id: int) -> dict[int, datetime]:
        """Members muted right now: account -> until when."""
        now = datetime.now(UTC)
        async with self.sessions() as session:
            rows = await session.execute(
                select(Membership.user_id, Membership.muted_until).where(
                    Membership.club_id == club_id, Membership.muted_until.is_not(None)
                )
            )
            return {int(u): aware(t) for u, t in rows.all() if t is not None and aware(t) > now}

    async def export(self, user_id: int) -> dict[str, Any]:
        """Everything kept about one account, for the person to download (the right of access)."""
        async with self.sessions() as session:
            user = await session.get(User, user_id)
            if user is None:
                return {}
            results = (await session.execute(select(Result).where(Result.user_id == user_id))).scalars().all()
            clubs = await session.execute(
                select(Club.name, Membership.role, Membership.joined_at)
                .join(Membership, Membership.club_id == Club.id)
                .where(Membership.user_id == user_id)
            )
            notes = (
                (await session.execute(select(Notification).where(Notification.user_id == user_id)))
                .scalars()
                .all()
            )
            prefs = await session.get(UserPrefs, user_id)
            ledger = (
                (
                    await session.execute(
                        select(LedgerEntry).where(LedgerEntry.user_id == user_id).order_by(LedgerEntry.id)
                    )
                )
                .scalars()
                .all()
            )
        friends = await self.friends(user_id)
        return {
            "account": {
                "username": user.username,
                "email": user.email,
                "email_verified": bool(user.email_verified),
                "coins": user.coins,
                "powerups": dict(user.powerups or {}),
                "created_at": aware(user.created_at).isoformat(),
            },
            "games": [
                {
                    "game": r.game_id,
                    "season": r.season,
                    "place": r.place,
                    "players": r.players,
                    "points": r.points,
                    "coins": r.coins,
                    "played_at": aware(r.played_at).isoformat(),
                }
                for r in results
            ],
            "coins": [
                {
                    "delta": e.delta,
                    "reason": e.reason,
                    "ref": f"{e.ref_type}:{e.ref_id}",
                    "at": aware(e.created_at).isoformat(),
                }
                for e in ledger
            ],
            "clubs": [
                {"club": n, "role": role, "joined_at": aware(at).isoformat()} for n, role, at in clubs.all()
            ],
            "friends": {k: [name for _, name in v] for k, v in friends.items()},
            "blocked": [name for name, _ in await self.blocked_by_me(user_id)],
            "notifications": [
                {"title": n.title, "body": n.body, "at": aware(n.created_at).isoformat()} for n in notes
            ],
            "settings": dict(prefs.data or {}) if prefs else {},
        }

    # -- places (places.py) -----------------------------------------------------------------------------
    async def place_for_domain(self, domain: str) -> Place | None:
        """The place an email domain belongs to: the domain itself or any parent ("cs.iitd.ac.in" ->
        "iitd.ac.in"), most specific first."""
        parts = domain.split(".")
        candidates = [".".join(parts[i:]) for i in range(len(parts) - 1)]
        async with self.sessions() as session:
            rows = await session.execute(
                select(PlaceDomain.domain, Place)
                .join(Place, Place.id == PlaceDomain.place_id)
                .where(PlaceDomain.domain.in_(candidates))
            )
            found = {d: place for d, place in rows.all()}
        return next((found[c] for c in candidates if c in found), None)

    async def note_place_request(self, domain: str) -> None:
        async with self.sessions() as session:
            row = await session.get(PlaceRequest, domain)
            if row is None:
                session.add(PlaceRequest(domain=domain))
            elif row.status == "open":
                row.count += 1
                row.last_at = datetime.now(UTC)
            await session.commit()

    async def place_email_owner(self, place_id: int, email_hash: str) -> int | None:
        async with self.sessions() as session:
            return await session.scalar(
                select(UserPlace.user_id).where(
                    UserPlace.place_id == place_id, UserPlace.email_hash == email_hash
                )
            )

    async def start_place_code(
        self, user_id: int, place_id: int, email_hash: str, code_hash: str, ttl: float
    ) -> None:
        async with self.sessions() as session:
            await session.execute(delete(PlaceCode).where(PlaceCode.user_id == user_id))
            session.add(
                PlaceCode(
                    user_id=user_id,
                    place_id=place_id,
                    email_hash=email_hash,
                    code_hash=code_hash,
                    expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
                )
            )
            await session.commit()

    async def place_code(self, user_id: int) -> PlaceCode | None:
        async with self.sessions() as session:
            return await session.get(PlaceCode, user_id)

    async def place_code_failed(self, user_id: int) -> None:
        async with self.sessions() as session:
            await session.execute(
                update(PlaceCode).where(PlaceCode.user_id == user_id).values(attempts=PlaceCode.attempts + 1)
            )
            await session.commit()

    async def verify_place(self, user_id: int, place_id: int, email_hash: str, days: int) -> bool:
        """Record the verification (or renew it). False if that address now proves another account."""
        now = datetime.now(UTC)
        async with self.sessions() as session:
            other = await session.scalar(
                select(UserPlace.user_id).where(
                    UserPlace.place_id == place_id,
                    UserPlace.email_hash == email_hash,
                    UserPlace.user_id != user_id,
                )
            )
            await session.execute(delete(PlaceCode).where(PlaceCode.user_id == user_id))
            if other is not None:
                await session.commit()
                return False
            row = await session.get(UserPlace, (user_id, place_id))
            if row is None:
                session.add(
                    UserPlace(
                        user_id=user_id,
                        place_id=place_id,
                        email_hash=email_hash,
                        verified_at=now,
                        expires_at=now + timedelta(days=days),
                    )
                )
            else:
                row.email_hash, row.verified_at, row.expires_at = email_hash, now, now + timedelta(days=days)
            await session.commit()
            return True

    async def user_places(self, user_ids: list[int]) -> dict[int, list[tuple[Place, datetime, datetime]]]:
        """account -> [(place, verified at, expires at)] for these accounts."""
        if not user_ids:
            return {}
        async with self.sessions() as session:
            rows = await session.execute(
                select(UserPlace.user_id, Place, UserPlace.verified_at, UserPlace.expires_at)
                .join(Place, Place.id == UserPlace.place_id)
                .where(UserPlace.user_id.in_(user_ids))
                .order_by(Place.name)
            )
            out: dict[int, list[tuple[Place, datetime, datetime]]] = {}
            for uid, place, at, until in rows.all():
                out.setdefault(int(uid), []).append((place, aware(at), aware(until)))
            return out

    async def remove_user_place(self, user_id: int, place_id: int) -> None:
        async with self.sessions() as session:
            await session.execute(
                delete(UserPlace).where(UserPlace.user_id == user_id, UserPlace.place_id == place_id)
            )
            await session.commit()

    async def place_by_slug(self, slug: str) -> Place | None:
        async with self.sessions() as session:
            return await session.scalar(select(Place).where(Place.slug == slug))

    async def places(self) -> list[tuple[Place, list[str], int]]:
        """Every place with its domains and how many accounts are verified there now."""
        now = datetime.now(UTC)
        async with self.sessions() as session:
            places = (await session.execute(select(Place).order_by(Place.name))).scalars().all()
            domains = await session.execute(
                select(PlaceDomain.place_id, PlaceDomain.domain).order_by(PlaceDomain.domain)
            )
            counts = await session.execute(
                select(UserPlace.place_id, func.count())
                .where(UserPlace.expires_at > now)
                .group_by(UserPlace.place_id)
            )
        by_place: dict[int, list[str]] = {}
        for pid, domain in domains.all():
            by_place.setdefault(int(pid), []).append(str(domain))
        members = {int(pid): int(n) for pid, n in counts.all()}
        return [(p, by_place.get(p.id, []), members.get(p.id, 0)) for p in places]

    async def save_place(self, slug: str, name: str, kind: str, domains: list[str]) -> str | None:
        """Create or update a place and its domains. Returns a domain already used by another place
        (nothing is saved then), else None."""
        async with self.sessions() as session:
            place = await session.scalar(select(Place).where(Place.slug == slug))
            if place is None:
                place = Place(slug=slug, name=name, kind=kind)
                session.add(place)
                await session.flush()
            else:
                place.name, place.kind = name, kind
            taken = await session.scalar(
                select(PlaceDomain.domain).where(
                    PlaceDomain.domain.in_(domains), PlaceDomain.place_id != place.id
                )
            )
            if taken is not None:
                await session.rollback()
                return str(taken)
            await session.execute(delete(PlaceDomain).where(PlaceDomain.place_id == place.id))
            for domain in domains:
                session.add(PlaceDomain(domain=domain, place_id=place.id))
            await session.execute(
                update(PlaceRequest).where(PlaceRequest.domain.in_(domains)).values(status="added")
            )
            await session.commit()
            return None

    async def place_requests(self) -> list[PlaceRequest]:
        async with self.sessions() as session:
            rows = await session.execute(
                select(PlaceRequest)
                .where(PlaceRequest.status == "open")
                .order_by(PlaceRequest.count.desc(), PlaceRequest.last_at.desc())
                .limit(100)
            )
            return list(rows.scalars().all())

    async def decline_place_request(self, domain: str) -> None:
        async with self.sessions() as session:
            await session.execute(
                update(PlaceRequest).where(PlaceRequest.domain == domain).values(status="declined")
            )
            await session.commit()

    # -- notifications (notify.py) ----------------------------------------------------------------------
    async def prefs(self, user_id: int) -> dict[str, Any]:
        async with self.sessions() as session:
            row = await session.get(UserPrefs, user_id)
            return dict(row.data or {}) if row else {}

    async def save_prefs(self, user_id: int, data: dict[str, Any]) -> None:
        async with self.sessions() as session:
            row = await session.get(UserPrefs, user_id)
            if row is None:
                session.add(UserPrefs(user_id=user_id, data=data))
            else:
                row.data = data
            await session.commit()

    async def count_notifications(self, user_id: int, scope: str, since: datetime) -> int:
        async with self.sessions() as session:
            n = await session.scalar(
                select(func.count()).where(
                    Notification.user_id == user_id,
                    Notification.scope == scope,
                    Notification.created_at >= since,
                )
            )
            return int(n or 0)

    async def count_pushed(self, user_id: int, since: datetime) -> int:
        async with self.sessions() as session:
            n = await session.scalar(
                select(func.count()).where(
                    Notification.user_id == user_id,
                    Notification.pushed.is_(True),
                    Notification.created_at >= since,
                )
            )
            return int(n or 0)

    async def add_notification(
        self,
        user_id: int,
        kind: str,
        scope: str,
        title: str,
        body: str,
        link: str,
        group_key: str | None,
        pushed: bool,
        group_since: datetime,
    ) -> None:
        """A new inbox entry, or an update to an unread one with the same group key. Keeps the newest
        INBOX_KEEP per person."""
        now = datetime.now(UTC)
        async with self.sessions() as session:
            row = None
            if group_key:
                found = await session.execute(
                    select(Notification)
                    .where(
                        Notification.user_id == user_id,
                        Notification.group_key == group_key,
                        Notification.read_at.is_(None),
                        Notification.created_at >= group_since,
                    )
                    .limit(1)
                )
                row = found.scalar_one_or_none()
            if row is not None:
                row.title, row.body, row.link, row.created_at = title, body, link, now
                row.pushed = row.pushed or pushed
            else:
                session.add(
                    Notification(
                        user_id=user_id,
                        kind=kind,
                        scope=scope,
                        title=title,
                        body=body,
                        link=link,
                        group_key=group_key,
                        pushed=pushed,
                        created_at=now,
                    )
                )
            await session.flush()
            old = await session.execute(
                select(Notification.id)
                .where(Notification.user_id == user_id)
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .offset(INBOX_KEEP)
            )
            ids = list(old.scalars().all())
            if ids:
                await session.execute(delete(Notification).where(Notification.id.in_(ids)))
            await session.commit()

    async def inbox(self, user_id: int, limit: int = 50) -> tuple[list[Notification], int]:
        async with self.sessions() as session:
            rows = await session.execute(
                select(Notification)
                .where(Notification.user_id == user_id)
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(limit)
            )
            unread = await session.scalar(
                select(func.count()).where(Notification.user_id == user_id, Notification.read_at.is_(None))
            )
            return list(rows.scalars().all()), int(unread or 0)

    async def mark_read(self, user_id: int, ids: list[int] | None) -> None:
        async with self.sessions() as session:
            where = [Notification.user_id == user_id, Notification.read_at.is_(None)]
            if ids is not None:
                where.append(Notification.id.in_(ids))
            await session.execute(update(Notification).where(*where).values(read_at=datetime.now(UTC)))
            await session.commit()

    async def push_subs(self, user_id: int) -> list[PushSub]:
        async with self.sessions() as session:
            rows = await session.execute(select(PushSub).where(PushSub.user_id == user_id))
            return list(rows.scalars().all())

    async def add_push_sub(self, user_id: int, endpoint: str, p256dh: str, auth: str, keep: int = 10) -> None:
        """Remember a browser's subscription (moving it to this account if another had it)."""
        async with self.sessions() as session:
            await session.execute(delete(PushSub).where(PushSub.endpoint == endpoint))
            session.add(PushSub(endpoint=endpoint, user_id=user_id, p256dh=p256dh, auth=auth))
            await session.flush()
            extra = await session.execute(
                select(PushSub.endpoint)
                .where(PushSub.user_id == user_id)
                .order_by(PushSub.created_at.desc())
                .offset(keep)
            )
            gone = list(extra.scalars().all())
            if gone:
                await session.execute(delete(PushSub).where(PushSub.endpoint.in_(gone)))
            await session.commit()

    async def delete_push_sub(self, endpoint: str, user_id: int | None = None) -> None:
        async with self.sessions() as session:
            where = [PushSub.endpoint == endpoint]
            if user_id is not None:
                where.append(PushSub.user_id == user_id)
            await session.execute(delete(PushSub).where(*where))
            await session.commit()

    async def club_names(self, ids: set[int]) -> dict[int, str]:
        if not ids:
            return {}
        async with self.sessions() as session:
            rows = await session.execute(select(Club.id, Club.name).where(Club.id.in_(ids)))
            return {int(i): str(n) for i, n in rows.all()}

    async def users_by_id(self, ids: list[int]) -> dict[int, User]:
        if not ids:
            return {}
        async with self.sessions() as session:
            rows = await session.execute(select(User).where(User.id.in_(ids)))
            return {u.id: u for u in rows.scalars().all()}

    async def circle(self, user_id: int) -> dict[str, Any]:
        """The host's belt holder and forfeits (empty when they have none, or the database is down)."""
        try:
            async with self.sessions() as session:
                row = await session.get(Circle, user_id)
            if row is not None:
                return {"belt": row.belt, "forfeits": [str(x) for x in (row.forfeits or [])]}
        except Exception:  # a room must open even if this can't be read
            log.exception("circle load failed")
        return {"belt": "", "forfeits": []}

    async def save_circle(self, user_id: int, belt: str, forfeits: list[str]) -> None:
        try:
            async with self.sessions() as session:
                row = await session.get(Circle, user_id)
                if row is None:
                    session.add(Circle(user_id=user_id, belt=belt, forfeits=list(forfeits)))
                else:
                    row.belt, row.forfeits = belt, list(forfeits)
                await session.commit()
        except Exception:
            log.exception("circle save failed")

    async def add_friend(self, user_id: int, friend_id: int) -> bool:
        """False when the list is full. Adding someone twice is fine."""
        async with self.sessions() as session:
            have = await session.execute(select(Friend.friend_id).where(Friend.user_id == user_id))
            mine = set(have.scalars())
            if friend_id in mine:
                return True
            if len(mine) >= MAX_FRIENDS:
                return False
            session.add(Friend(user_id=user_id, friend_id=friend_id))
            await session.commit()
            return True

    async def remove_friend(self, user_id: int, friend_id: int) -> None:
        async with self.sessions() as session:
            await session.execute(
                delete(Friend).where(Friend.user_id == user_id, Friend.friend_id == friend_id)
            )
            await session.commit()

    async def friends(self, user_id: int) -> dict[str, list[tuple[int, str]]]:
        """(id, username) lists: 'mutual' (both added), 'sent' (only I added), 'asked' (only they added)."""
        async with self.sessions() as session:
            out = await session.execute(
                select(User.id, User.username)
                .join(Friend, Friend.friend_id == User.id)
                .where(Friend.user_id == user_id)
            )
            back = await session.execute(
                select(User.id, User.username)
                .join(Friend, Friend.user_id == User.id)
                .where(Friend.friend_id == user_id)
            )
        mine = {int(i): str(n) for i, n in out.all()}
        theirs = {int(i): str(n) for i, n in back.all()}
        by_name = lambda pairs: sorted(pairs, key=lambda p: p[1].casefold())  # noqa: E731
        return {
            "mutual": by_name((i, n) for i, n in mine.items() if i in theirs),
            "sent": by_name((i, n) for i, n in mine.items() if i not in theirs),
            "asked": by_name((i, n) for i, n in theirs.items() if i not in mine),
        }

    async def buy(self, user_id: int, item: str, price: int) -> User | None:
        """Spend coins on a power-up in one step: None (and nothing spent) if there aren't enough."""
        async with self.sessions() as session:
            row = await session.execute(select(User).where(User.id == user_id).with_for_update())
            user = row.scalar_one_or_none()
            if user is None or user.coins < price:
                return None
            await self._post(session, user_id, -price, "shop", "item", f"{item}:{secrets.token_hex(6)}")
            await session.refresh(user)
            owned = dict(user.powerups or {})
            owned[item] = owned.get(item, 0) + 1
            user.powerups = owned
            await session.commit()
            return user

    async def spend_powerup(self, user_id: int, item: str) -> bool:
        """Use one owned power-up (False if there's none left)."""
        try:
            async with self.sessions() as session:
                row = await session.execute(select(User).where(User.id == user_id).with_for_update())
                user = row.scalar_one_or_none()
                owned = dict(user.powerups or {}) if user else {}
                if user is None or owned.get(item, 0) < 1:
                    return False
                owned[item] -= 1
                if not owned[item]:
                    del owned[item]
                user.powerups = owned
                await session.commit()
                return True
        except Exception:
            log.exception("could not spend a power-up")
            return False

    async def refund_powerup(self, user_id: int, item: str) -> None:
        try:
            async with self.sessions() as session:
                row = await session.execute(select(User).where(User.id == user_id).with_for_update())
                user = row.scalar_one_or_none()
                if user is not None:
                    owned = dict(user.powerups or {})
                    owned[item] = owned.get(item, 0) + 1
                    user.powerups = owned
                    await session.commit()
        except Exception:
            log.exception("could not refund a power-up")

    async def record_results(self, rows: list[dict[str, Any]], season: str, daily_cap: int) -> dict[int, int]:
        """Store each account's finish and pay its coins (up to the daily cap). Returns coins paid."""
        paid: dict[int, int] = {}
        if not self.ready or not rows:
            return paid
        try:
            async with self.sessions() as session:
                since = datetime.now(UTC) - timedelta(days=1)
                # Lock each account (in id order: no deadlocks) before reading its day's total, so two
                # rooms finishing at the same moment can't both pay up to the cap. (SQLite ignores the
                # lock; it serialises writers anyway.)
                for r in sorted(rows, key=lambda r: r["user_id"]):
                    await session.execute(select(User.id).where(User.id == r["user_id"]).with_for_update())
                    left = max(0, daily_cap - await self._earned_since(session, r["user_id"], since))
                    coins = min(r["coins"], left)
                    result = Result(
                        user_id=r["user_id"],
                        game_id=r["game_id"],
                        season=season,
                        place=r["place"],
                        players=r["players"],
                        points=r["points"],
                        coins=coins,
                    )
                    session.add(result)
                    await session.flush()
                    if coins:
                        await self._post(session, r["user_id"], coins, "place", "result", str(result.id))
                    paid[r["user_id"]] = coins
                await session.commit()
        except Exception:
            log.exception("could not record account results")
            return {}
        return paid

    # -- the coin ledger ----------------------------------------------------------------------------------
    @staticmethod
    async def _post(session: Any, user_id: int, delta: int, reason: str, ref_type: str, ref_id: str) -> bool:
        """Append one ledger row and move the cached balance with it, in the caller's transaction.
        False (and nothing changes) if that reason and reference were already posted."""
        try:
            async with session.begin_nested():
                session.add(
                    LedgerEntry(
                        user_id=user_id, delta=delta, reason=reason, ref_type=ref_type, ref_id=ref_id[:64]
                    )
                )
                await session.flush()
        except IntegrityError:
            return False
        await session.execute(update(User).where(User.id == user_id).values(coins=User.coins + delta))
        return True

    @staticmethod
    async def _earned_since(session: Any, user_id: int, since: datetime) -> int:
        """Coins earned by playing since then (what the daily cap counts)."""
        got = await session.scalar(
            select(func.coalesce(func.sum(LedgerEntry.delta), 0)).where(
                LedgerEntry.user_id == user_id,
                LedgerEntry.reason == "place",
                LedgerEntry.created_at >= since,
            )
        )
        return int(got or 0)

    async def coin_history(self, user_id: int, limit: int = 50) -> dict[str, Any]:
        """Your balance, what you've earned today toward the cap, and the latest ledger rows (with the
        game behind each finish)."""
        async with self.sessions() as session:
            user = await session.get(User, user_id)
            earned = await self._earned_since(session, user_id, datetime.now(UTC) - timedelta(days=1))
            rows = (
                (
                    await session.execute(
                        select(LedgerEntry)
                        .where(LedgerEntry.user_id == user_id)
                        .order_by(LedgerEntry.id.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            result_ids = [int(r.ref_id) for r in rows if r.ref_type == "result" and r.ref_id.isdigit()]
            results = (
                {
                    res.id: res
                    for res in (
                        await session.execute(select(Result).where(Result.id.in_(result_ids)))
                    ).scalars()
                }
                if result_ids
                else {}
            )
        entries = []
        for r in rows:
            res = results.get(int(r.ref_id)) if r.ref_type == "result" and r.ref_id.isdigit() else None
            entries.append(
                {
                    "delta": r.delta,
                    "reason": r.reason,
                    "ref": r.ref_id.split(":")[0] if r.ref_type in ("item", "rating") else None,
                    "season": int(r.ref_id.split(":")[1]) if r.ref_type == "rating" else None,
                    "game": res.game_id if res else None,
                    "place": res.place if res else None,
                    "at": aware(r.created_at).isoformat(),
                }
            )
        return {"balance": user.coins if user else 0, "earned_today": earned, "entries": entries}

    async def _season_reward(self, session: Any, row: SkillRating, season: int) -> dict[str, Any] | None:
        """A rating last played in an earlier season: pay that season's reward for the tier it ended
        on, once."""
        if row.season >= season:
            return None
        shown = ratinglib.Rating(row.mu, row.sigma).display
        tier = ratinglib.tier(shown, row.games)
        coins = ratinglib.SEASON_REWARD.get(tier, 0)
        if not coins:
            return None
        if not await self._post(
            session, row.user_id, coins, "season", "rating", f"{row.game_id}:{row.season}"
        ):
            return None
        return {"game": row.game_id, "season": row.season, "tier": tier, "coins": coins}

    # -- ratings (ratings.py) ---------------------------------------------------------------------------
    @staticmethod
    def _current(row: SkillRating | None, season: int) -> tuple[ratinglib.Rating, int]:
        """A stored rating as it stands this season, and its game count."""
        if row is None:
            return ratinglib.Rating(), 0
        return ratinglib.soft_reset(ratinglib.Rating(row.mu, row.sigma), season - row.season), row.games

    async def rate_match(self, game_id: str, placing: dict[int, int]) -> dict[int, dict[str, Any]] | None:
        """Rate one ranked game. `placing`: account -> place (1 = best, ties share). Returns each
        account's change, or None when the game doesn't count (two accounts that already met
        ratings.PAIR_LIMIT times today)."""
        if not self.ready or len(placing) < 2:
            return None
        season = ratinglib.season_of()
        since = datetime.now(UTC) - timedelta(days=1)
        ids = sorted(placing)
        async with self.sessions() as session:
            for uid in ids:  # one writer per account at a time (id order: no deadlocks)
                await session.execute(select(User.id).where(User.id == uid).with_for_update())
            if len(ids) == 2:
                a, b = ids
                theirs = select(RatingEvent.match).where(RatingEvent.user_id == b, RatingEvent.at >= since)
                met = await session.scalar(
                    select(func.count()).where(
                        RatingEvent.user_id == a, RatingEvent.at >= since, RatingEvent.match.in_(theirs)
                    )
                )
                if (met or 0) >= ratinglib.PAIR_LIMIT:
                    return None
            rows = {
                r.user_id: r
                for r in (
                    await session.execute(
                        select(SkillRating).where(
                            SkillRating.user_id.in_(ids), SkillRating.game_id == game_id
                        )
                    )
                ).scalars()
            }
            moved = dict(
                (
                    await session.execute(
                        select(RatingEvent.user_id, func.sum(RatingEvent.after - RatingEvent.before))
                        .where(
                            RatingEvent.user_id.in_(ids),
                            RatingEvent.game_id == game_id,
                            RatingEvent.at >= since,
                        )
                        .group_by(RatingEvent.user_id)
                    )
                ).all()
            )
            for row in rows.values():
                await self._season_reward(session, row, season)
            now = {uid: self._current(rows.get(uid), season) for uid in ids}
            new = ratinglib.rate({str(u): now[u][0] for u in ids}, {str(u): placing[u] for u in ids})
            match = secrets.token_hex(12)
            out: dict[int, dict[str, Any]] = {}
            for uid in ids:
                old, games = now[uid]
                rating = ratinglib.capped(old, new[str(uid)], int(moved.get(uid) or 0))
                row = rows.get(uid)
                if row is None:
                    row = SkillRating(user_id=uid, game_id=game_id, games=0)
                    session.add(row)
                row.mu, row.sigma, row.season = rating.mu, rating.sigma, season
                row.games = games + 1
                row.updated_at = datetime.now(UTC)
                session.add(
                    RatingEvent(
                        match=match,
                        user_id=uid,
                        game_id=game_id,
                        season=season,
                        place=placing[uid],
                        before=old.display,
                        after=rating.display,
                    )
                )
                out[uid] = {
                    "before": old.display,
                    "after": rating.display,
                    "games": games + 1,
                    "tier": ratinglib.tier(rating.display, games + 1),
                }
            await session.commit()
        return out

    async def my_ratings(self, user_id: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Your ratings as they stand this season, and any season rewards this paid just now."""
        season = ratinglib.season_of()
        async with self.sessions() as session:
            rows = list(
                (await session.execute(select(SkillRating).where(SkillRating.user_id == user_id))).scalars()
            )
            out, paid = [], []
            for row in rows:
                reward = await self._season_reward(session, row, season)
                if reward:
                    paid.append(reward)
                rating, games = self._current(row, season)
                out.append({"game": row.game_id, "rating": rating.display, "games": games})
            if paid:
                await session.commit()
            return out, paid

    async def rating_board(
        self, game_id: str, user_ids: set[int] | None, week: bool, limit: int = 50
    ) -> list[dict[str, Any]]:
        """The top of one game's board this season (rating) or this week (rating gained), among
        `user_ids` (None: everyone). Provisional players aren't listed."""
        season = ratinglib.season_of()
        async with self.sessions() as session:
            if week:
                gain = func.sum(RatingEvent.after - RatingEvent.before)
                q = (
                    select(User.username, gain, SkillRating.mu, SkillRating.sigma, SkillRating.games)
                    .join(User, User.id == RatingEvent.user_id)
                    .join(
                        SkillRating,
                        (SkillRating.user_id == RatingEvent.user_id) & (SkillRating.game_id == game_id),
                    )
                    .where(
                        RatingEvent.game_id == game_id,
                        RatingEvent.at >= datetime.now(UTC) - timedelta(days=7),
                        SkillRating.games >= ratinglib.PROVISIONAL_GAMES,
                    )
                    .group_by(User.username, SkillRating.mu, SkillRating.sigma, SkillRating.games)
                    .order_by(gain.desc(), User.username)
                    .limit(limit)
                )
                if user_ids is not None:
                    q = q.where(RatingEvent.user_id.in_(user_ids))
                rows = (await session.execute(q)).all()
                return [
                    {
                        "username": name,
                        "rating": ratinglib.Rating(mu, sigma).display,
                        "tier": ratinglib.tier(ratinglib.Rating(mu, sigma).display, games),
                        "games": games,
                        "gain": int(g or 0),
                    }
                    for name, g, mu, sigma, games in rows
                ]
            q = (
                select(User.username, SkillRating.mu, SkillRating.sigma, SkillRating.games)
                .join(User, User.id == SkillRating.user_id)
                .where(
                    SkillRating.game_id == game_id,
                    SkillRating.season == season,
                    SkillRating.games >= ratinglib.PROVISIONAL_GAMES,
                )
                # the shown number is mu - 3 sigma: order by it, ties by name
                .order_by((SkillRating.mu - 3 * SkillRating.sigma).desc(), User.username)
                .limit(limit)
            )
            if user_ids is not None:
                q = q.where(SkillRating.user_id.in_(user_ids))
            out = []
            for name, mu, sigma, games in (await session.execute(q)).all():
                shown = ratinglib.Rating(mu, sigma).display
                out.append(
                    {
                        "username": name,
                        "rating": shown,
                        "tier": ratinglib.tier(shown, games),
                        "games": games,
                        "gain": None,
                    }
                )
            return out

    async def club_member_ids(self, club_id: int) -> set[int]:
        async with self.sessions() as session:
            rows = await session.execute(
                select(Membership.user_id).where(Membership.club_id == club_id, Membership.banned.is_(False))
            )
            return set(rows.scalars())

    async def place_board_ids(self, place_id: int) -> set[int]:
        """Accounts verified at the place now that chose to be on its boards."""
        async with self.sessions() as session:
            rows = await session.execute(
                select(UserPlace.user_id)
                .join(User, User.id == UserPlace.user_id)
                .where(
                    UserPlace.place_id == place_id,
                    UserPlace.expires_at > datetime.now(UTC),
                    User.place_boards.is_(True),
                )
            )
            return set(rows.scalars())

    async def set_place_boards(self, user_id: int, on: bool) -> None:
        async with self.sessions() as session:
            await session.execute(update(User).where(User.id == user_id).values(place_boards=on))
            await session.commit()

    async def user_stats(self, user_id: int, season: str) -> dict[str, Any]:
        wins = func.sum(func.cast(Result.place == 1, Integer))
        async with self.sessions() as session:
            rows = (
                await session.execute(
                    select(
                        Result.game_id, func.count(), wins, func.max(Result.points), func.sum(Result.coins)
                    )
                    .where(Result.user_id == user_id)
                    .group_by(Result.game_id)
                )
            ).all()
            mine = (
                await session.execute(
                    select(func.count(), wins, func.sum(Result.coins)).where(
                        Result.user_id == user_id, Result.season == season
                    )
                )
            ).one()
        games = {
            g: {"played": int(n), "wins": int(w or 0), "best": int(b or 0), "coins": int(c or 0)}
            for g, n, w, b, c in rows
        }
        board = await self.leaderboard(season, 1000)
        rank = next((i + 1 for i, r in enumerate(board) if r["user_id"] == user_id), None)
        return {
            "games": games,
            "totals": {
                "played": sum(v["played"] for v in games.values()),
                "wins": sum(v["wins"] for v in games.values()),
                "coins": sum(v["coins"] for v in games.values()),
            },
            "season": {
                "id": season,
                "played": int(mine[0] or 0),
                "wins": int(mine[1] or 0),
                "points": int(mine[2] or 0),
                "rank": rank,
            },
        }

    async def leaderboard(self, season: str, limit: int) -> list[dict[str, Any]]:
        """This season's table: coins earned this month (wins break ties)."""
        wins = func.sum(func.cast(Result.place == 1, Integer))
        points = func.sum(Result.coins)
        try:
            async with self.sessions() as session:
                rows = (
                    await session.execute(
                        select(User.id, User.username, points, wins, func.count())
                        .join(Result, Result.user_id == User.id)
                        .where(Result.season == season)
                        .group_by(User.id, User.username)
                        .order_by(points.desc(), wins.desc(), User.id)
                        .limit(limit)
                    )
                ).all()
        except Exception:
            log.exception("could not read the leaderboard")
            return []
        return [
            {"user_id": uid, "username": name, "points": int(p or 0), "wins": int(w or 0), "played": int(n)}
            for uid, name, p, w, n in rows
        ]

    async def close(self) -> None:
        await self.engine.dispose()


def suspended(user: User) -> bool:
    return user.suspended_until is not None and aware(user.suspended_until) > datetime.now(UTC)


def aware(when: datetime) -> datetime:
    """SQLite hands back naive datetimes (stored as UTC); Postgres keeps the zone."""
    return when if when.tzinfo else when.replace(tzinfo=UTC)
