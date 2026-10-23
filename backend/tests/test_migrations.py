"""Schema migrations: a new database migrates to exactly the models, a database from before migrations is
stamped (its data kept), and every migration can be rolled back."""

from __future__ import annotations

import os
import unittest

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, insert, inspect, select, text

from app.db import BASELINE, MIGRATIONS, Base, User, make_engine, migrate


def config(conn: Connection) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.attributes["connection"] = conn
    return cfg


def revision(conn: Connection) -> str | None:
    return MigrationContext.configure(conn).get_current_revision()


def drift(conn: Connection) -> list[object]:
    return compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)


class MigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        # MIGRATION_TEST_URL runs the same checks on Postgres (production's database); it is emptied first.
        url = os.environ.get("MIGRATION_TEST_URL", "sqlite+aiosqlite:///:memory:")
        self.engine = make_engine(url)
        if url.startswith("postgresql"):
            async with self.engine.begin() as conn:
                await conn.execute(text("DROP SCHEMA public CASCADE"))
                await conn.execute(text("CREATE SCHEMA public"))

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_a_new_database_matches_the_models(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(migrate)
            self.assertIsNotNone(await conn.run_sync(revision))
            self.assertEqual(await conn.run_sync(drift), [])  # a model change needs a migration

    async def test_a_database_from_before_migrations_is_stamped_and_keeps_its_data(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)  # how the app made its tables before
            await conn.execute(
                insert(User).values(
                    username="Ana", username_key="ana", pw_hash="x", recovery_hash="y", coins=7, powerups={}
                )
            )
            await conn.run_sync(migrate)
            self.assertIsNotNone(await conn.run_sync(revision))
            coins = (await conn.execute(select(User.coins).where(User.username_key == "ana"))).scalar_one()
            self.assertEqual(coins, 7)
            await conn.run_sync(migrate)  # running again changes nothing

    async def test_every_migration_rolls_back(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(migrate)
            await conn.run_sync(lambda c: command.downgrade(config(c), "base"))
            tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
            self.assertEqual([t for t in tables if t != "alembic_version"], [])
            await conn.run_sync(lambda c: command.upgrade(config(c), "head"))
            self.assertEqual(await conn.run_sync(drift), [])

    def test_the_baseline_is_the_first_revision(self):
        from alembic.script import ScriptDirectory

        cfg = Config()
        cfg.set_main_option("script_location", str(MIGRATIONS))
        self.assertEqual(ScriptDirectory.from_config(cfg).get_base(), BASELINE)
