"""Optional persistence: anonymous per-game results, generated content, and snapshots of live rooms
(so a restart or a deploy doesn't end a game). Game results hold no names, IPs or tokens; a room
snapshot holds what the room holds (display names, scores) and is deleted when the room ends.

The game never depends on the database: every call here fails soft.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

log = logging.getLogger("snazzlebop.db")


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


class Session(Base):
    """A signed-in browser. Only the SHA-256 of the cookie's token is kept."""

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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


def make_engine(url: str) -> AsyncEngine:
    if url.startswith("sqlite"):
        kwargs: dict[str, Any] = {}
        if ":memory:" in url:
            kwargs.update(poolclass=StaticPool, connect_args={"check_same_thread": False})
        return create_async_engine(url, **kwargs)
    return create_async_engine(url, pool_size=5, max_overflow=5, pool_recycle=1800, pool_pre_ping=True)


class Database:
    def __init__(self, url: str) -> None:
        self.engine = make_engine(url)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.ready = False

    async def init(self) -> None:
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
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
                    select(User, Session.expires_at)
                    .join(Session, Session.user_id == User.id)
                    .where(Session.token_hash == token_hash)
                )
                found = row.first()
                if found is None:
                    return None
                user, expires = found
                if _aware(expires) < datetime.now(UTC):
                    await session.execute(delete(Session).where(Session.token_hash == token_hash))
                    await session.commit()
                    return None
                return user
        except Exception:
            log.exception("could not read a session")
            return None

    async def create_session(self, token_hash: str, user_id: int, ttl_seconds: float) -> None:
        async with self.sessions() as session:
            expires = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
            session.add(Session(token_hash=token_hash, user_id=user_id, expires_at=expires))
            await session.execute(delete(Session).where(Session.expires_at < datetime.now(UTC)))
            await session.commit()

    async def delete_session(self, token_hash: str) -> None:
        async with self.sessions() as session:
            await session.execute(delete(Session).where(Session.token_hash == token_hash))
            await session.commit()

    async def delete_sessions(self, user_id: int) -> None:
        async with self.sessions() as session:
            await session.execute(delete(Session).where(Session.user_id == user_id))
            await session.commit()

    async def set_credentials(self, user_id: int, pw_hash: str, recovery_hash: str | None) -> None:
        values: dict[str, Any] = {"pw_hash": pw_hash}
        if recovery_hash is not None:
            values["recovery_hash"] = recovery_hash
        async with self.sessions() as session:
            await session.execute(update(User).where(User.id == user_id).values(**values))
            await session.commit()

    async def delete_user(self, user_id: int) -> None:
        """The account and everything tied to it: sessions, results, coins, power-ups."""
        async with self.sessions() as session:
            await session.execute(delete(Session).where(Session.user_id == user_id))
            await session.execute(delete(Result).where(Result.user_id == user_id))
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()

    async def buy(self, user_id: int, item: str, price: int) -> User | None:
        """Spend coins on a power-up in one step: None (and nothing spent) if there aren't enough."""
        async with self.sessions() as session:
            row = await session.execute(select(User).where(User.id == user_id).with_for_update())
            user = row.scalar_one_or_none()
            if user is None or user.coins < price:
                return None
            user.coins -= price
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
                for r in rows:
                    got = await session.execute(
                        select(func.coalesce(func.sum(Result.coins), 0)).where(
                            Result.user_id == r["user_id"], Result.played_at >= since
                        )
                    )
                    left = max(0, daily_cap - int(got.scalar_one()))
                    coins = min(r["coins"], left)
                    session.add(
                        Result(
                            user_id=r["user_id"],
                            game_id=r["game_id"],
                            season=season,
                            place=r["place"],
                            players=r["players"],
                            points=r["points"],
                            coins=coins,
                        )
                    )
                    if coins:
                        await session.execute(
                            update(User).where(User.id == r["user_id"]).values(coins=User.coins + coins)
                        )
                    paid[r["user_id"]] = coins
                await session.commit()
        except Exception:
            log.exception("could not record account results")
            return {}
        return paid

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


def _aware(when: datetime) -> datetime:
    """SQLite hands back naive datetimes (stored as UTC); Postgres keeps the zone."""
    return when if when.tzinfo else when.replace(tzinfo=UTC)
