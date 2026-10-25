"""More quests: what players do in rooms that quests count (activity), and the day's quest reroll.

Revision ID: 0017
Revises: 0016
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("activity", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_activity_at"), ["at"], unique=False)
        batch_op.create_index(batch_op.f("ix_activity_user_id"), ["user_id"], unique=False)
    op.create_table(
        "quest_rerolls",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("old", sa.String(length=32), nullable=False),
        sa.Column("new", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "day"),
    )


def downgrade() -> None:
    op.drop_table("quest_rerolls")
    with op.batch_alter_table("activity", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_activity_user_id"))
        batch_op.drop_index(batch_op.f("ix_activity_at"))
    op.drop_table("activity")
