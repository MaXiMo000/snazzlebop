"""Schema migrations: a new database migrates to exactly the models, a database from before migrations is
stamped (its data kept), and every migration can be rolled back."""

from __future__ import annotations

import os
import unittest

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, inspect, select, text

from app.db import BASELINE, MIGRATIONS, Base, User, make_engine, migrate

BASELINE_TABLES = {
    "content_items",
    "game_results",
    "room_snapshots",
    "users",
    "circles",
    "friends",
    "results",
    "sessions",
}
# Columns later migrations added to those tables: a pre-migration database doesn't have them.
LATER_COLUMNS = {
    "results": ["group_key"],
    "users": ["email", "email_verified", "suspended_until", "suspend_reason", "place_boards"],
    "sessions": ["device", "created_at", "last_seen"],
}
LATER_INDEXES = ["ix_users_email"]


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
            # How the app made its tables before migrations: the baseline's eight, not today's models.
            await conn.run_sync(
                lambda c: Base.metadata.create_all(
                    c, tables=[t for t in Base.metadata.sorted_tables if t.name in BASELINE_TABLES]
                )
            )
            for index in LATER_INDEXES:
                await conn.execute(text(f"DROP INDEX {index}"))
            for table, columns in LATER_COLUMNS.items():
                for column in columns:
                    await conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
            await conn.execute(
                text(
                    "INSERT INTO users (username, username_key, pw_hash, recovery_hash, coins, powerups, created_at)"
                    " VALUES ('Ana', 'ana', 'x', 'y', 7, '{}', CURRENT_TIMESTAMP)"
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

    async def test_reports_from_before_cases_get_a_public_id(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(lambda c: command.upgrade(config(c), "0006"))
            await conn.execute(
                text(
                    "INSERT INTO reports (target_name, reason, note, context, status, created_at)"
                    " VALUES ('Bo', 'spam', '', '[]', 'open', CURRENT_TIMESTAMP)"
                )
            )
            await conn.run_sync(lambda c: command.upgrade(config(c), "head"))
            row = (await conn.execute(text("SELECT public_id, priority FROM reports"))).one()
            self.assertTrue(row[0].startswith("rpt_"))
            self.assertEqual(row[1], "normal")

    async def test_existing_balances_open_the_ledger(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(lambda c: command.upgrade(config(c), "0012"))
            await conn.execute(
                text(
                    "INSERT INTO users (username, username_key, pw_hash, recovery_hash, coins, powerups,"
                    " created_at, email_verified, place_boards) VALUES"
                    " ('Ana_99', 'ana_99', 'x', 'y', 120, '{}', CURRENT_TIMESTAMP, false, false),"
                    " ('Bo_42', 'bo_42', 'x', 'y', 0, '{}', CURRENT_TIMESTAMP, false, false)"
                )
            )
            await conn.run_sync(lambda c: command.upgrade(config(c), "head"))
            rows = (await conn.execute(text("SELECT delta, reason FROM ledger"))).all()
            self.assertEqual([tuple(r) for r in rows], [(120, "opening")])

    def test_the_baseline_is_the_first_revision(self):
        from alembic.script import ScriptDirectory

        cfg = Config()
        cfg.set_main_option("script_location", str(MIGRATIONS))
        self.assertEqual(ScriptDirectory.from_config(cfg).get_base(), BASELINE)
