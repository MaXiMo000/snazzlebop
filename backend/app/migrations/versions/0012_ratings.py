"""Ratings for ranked games, their history, and the choice to appear on place leaderboards.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ratings",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.String(length=32), nullable=False),
        sa.Column("mu", sa.Float(), nullable=False),
        sa.Column("sigma", sa.Float(), nullable=False),
        sa.Column("games", sa.Integer(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "game_id"),
    )
    with op.batch_alter_table("ratings", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_ratings_season"), ["season"], unique=False)
    op.create_table(
        "rating_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("match", sa.String(length=24), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.String(length=32), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("place", sa.Integer(), nullable=False),
        sa.Column("before", sa.Integer(), nullable=False),
        sa.Column("after", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("rating_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_rating_events_at"), ["at"], unique=False)
        batch_op.create_index(batch_op.f("ix_rating_events_match"), ["match"], unique=False)
        batch_op.create_index(batch_op.f("ix_rating_events_user_id"), ["user_id"], unique=False)
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("place_boards", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("place_boards")
    with op.batch_alter_table("rating_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_rating_events_user_id"))
        batch_op.drop_index(batch_op.f("ix_rating_events_match"))
        batch_op.drop_index(batch_op.f("ix_rating_events_at"))
    op.drop_table("rating_events")
    with op.batch_alter_table("ratings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ratings_season"))
    op.drop_table("ratings")
