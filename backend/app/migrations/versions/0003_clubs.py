"""Clubs: clubs, memberships (role, banned) and invite links (hashed codes that expire).

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clubs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=48), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("about", sa.String(length=200), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("clubs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_clubs_slug"), ["slug"], unique=True)

    op.create_table(
        "club_invites",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("uses_left", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("club_invites", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_club_invites_club_id"), ["club_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_club_invites_code_hash"), ["code_hash"], unique=True)

    op.create_table(
        "memberships",
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.Column("banned", sa.Boolean(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("club_id", "user_id"),
    )
    with op.batch_alter_table("memberships", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_memberships_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("memberships", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_memberships_user_id"))

    op.drop_table("memberships")
    with op.batch_alter_table("club_invites", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_club_invites_code_hash"))
        batch_op.drop_index(batch_op.f("ix_club_invites_club_id"))

    op.drop_table("club_invites")
    with op.batch_alter_table("clubs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_clubs_slug"))

    op.drop_table("clubs")
