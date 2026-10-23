"""Alembic environment. The app runs migrations on its own connection at startup (app.db.Database.init
passes it in `config.attributes["connection"]`); the command line uses DATABASE_URL instead."""

from __future__ import annotations

import asyncio
import os

from alembic import context
from sqlalchemy.engine import Connection

from app.config import Settings, normalize_database_url
from app.db import Base, make_engine

target_metadata = Base.metadata


def run(connection: Connection) -> None:
    # Batch mode lets SQLite (local dev, tests) apply column changes it can't ALTER in place.
    context.configure(
        connection=connection, target_metadata=target_metadata, render_as_batch=True, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_from_url() -> None:
    url = normalize_database_url(os.environ.get("DATABASE_URL", Settings().database_url))
    engine = make_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(run)
    await engine.dispose()


connection = context.config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    asyncio.run(run_from_url())
