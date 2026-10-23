"""Baseline: the eight tables as they stood before migrations (an older database is stamped with this).

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "key"),
    )
    with op.batch_alter_table("content_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_content_items_kind"), ["kind"], unique=False)

    op.create_table(
        "game_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.String(length=32), nullable=False),
        sa.Column("played_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("game_results", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_game_results_game_id"), ["game_id"], unique=False)

    op.create_table(
        "room_snapshots",
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )
    with op.batch_alter_table("room_snapshots", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_room_snapshots_updated_at"), ["updated_at"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=20), nullable=False),
        sa.Column("username_key", sa.String(length=20), nullable=False),
        sa.Column("pw_hash", sa.String(length=200), nullable=False),
        sa.Column("recovery_hash", sa.String(length=64), nullable=False),
        sa.Column("coins", sa.Integer(), nullable=False),
        sa.Column("powerups", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_username_key"), ["username_key"], unique=True)

    op.create_table(
        "circles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("belt", sa.String(length=32), nullable=False),
        sa.Column("forfeits", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "friends",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("friend_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["friend_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "friend_id"),
    )
    with op.batch_alter_table("friends", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_friends_friend_id"), ["friend_id"], unique=False)

    op.create_table(
        "results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.String(length=32), nullable=False),
        sa.Column("season", sa.String(length=7), nullable=False),
        sa.Column("place", sa.Integer(), nullable=False),
        sa.Column("players", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("coins", sa.Integer(), nullable=False),
        sa.Column("played_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("results", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_results_season"), ["season"], unique=False)
        batch_op.create_index(batch_op.f("ix_results_user_id"), ["user_id"], unique=False)

    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sessions_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sessions_user_id"))

    op.drop_table("sessions")
    with op.batch_alter_table("results", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_results_user_id"))
        batch_op.drop_index(batch_op.f("ix_results_season"))

    op.drop_table("results")
    with op.batch_alter_table("friends", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_friends_friend_id"))

    op.drop_table("friends")
    op.drop_table("circles")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_username_key"))

    op.drop_table("users")
    with op.batch_alter_table("room_snapshots", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_room_snapshots_updated_at"))

    op.drop_table("room_snapshots")
    with op.batch_alter_table("game_results", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_game_results_game_id"))

    op.drop_table("game_results")
    with op.batch_alter_table("content_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_content_items_kind"))

    op.drop_table("content_items")
