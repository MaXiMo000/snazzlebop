"""Levels and daily quests: XP (an append-only history and a cached total), who has played whom, and
whether a finished game counts for them.

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("xp", sa.Integer(), nullable=False, server_default="0"))
    with op.batch_alter_table("results", schema=None) as batch_op:
        batch_op.add_column(sa.Column("fair", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "xp_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=16), nullable=False),
        sa.Column("ref", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "reason", "ref"),
    )
    with op.batch_alter_table("xp_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_xp_events_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_xp_events_user_id"), ["user_id"], unique=False)
    op.create_table(
        "connections",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("other_id", sa.Integer(), nullable=False),
        sa.Column("first_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("games", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["other_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "other_id"),
    )


def downgrade() -> None:
    op.drop_table("connections")
    with op.batch_alter_table("xp_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_xp_events_user_id"))
        batch_op.drop_index(batch_op.f("ix_xp_events_created_at"))
    op.drop_table("xp_events")
    with op.batch_alter_table("results", schema=None) as batch_op:
        batch_op.drop_column("fair")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("xp")
