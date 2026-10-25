"""Battles between club members and each player's finish and prize.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "battles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=True),
        sa.Column("room_code", sa.String(length=8), nullable=False),
        sa.Column("game_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("challenger_id", sa.Integer(), nullable=False),
        sa.Column("opponent_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("played_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["challenger_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["opponent_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("battles", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_battles_challenger_id"), ["challenger_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_battles_opponent_id"), ["opponent_id"], unique=False)
    op.create_table(
        "battle_results",
        sa.Column("battle_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("place", sa.Integer(), nullable=False),
        sa.Column("finished", sa.Boolean(), nullable=False),
        sa.Column("prize", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["battle_id"], ["battles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("battle_id", "user_id"),
    )
    with op.batch_alter_table("battle_results", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_battle_results_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("battle_results", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_battle_results_user_id"))
    op.drop_table("battle_results")
    with op.batch_alter_table("battles", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_battles_opponent_id"))
        batch_op.drop_index(batch_op.f("ix_battles_challenger_id"))
    op.drop_table("battles")
