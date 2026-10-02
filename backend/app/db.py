"""Optional persistence: anonymous per-game results only. No names, IPs or tokens are stored.

The game never depends on the database: every call here fails soft.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint, func, select
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

    async def close(self) -> None:
        await self.engine.dispose()
