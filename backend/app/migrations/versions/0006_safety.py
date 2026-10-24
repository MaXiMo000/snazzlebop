"""Safety: blocks, reports, the moderators' audit log, and club mutes.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("memberships", schema=None) as batch_op:
        batch_op.add_column(sa.Column("muted_until", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "blocks",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("blocked_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blocked_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "blocked_id"),
    )
    with op.batch_alter_table("blocks", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_blocks_blocked_id"), ["blocked_id"], unique=False)

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("reporter_id", sa.Integer(), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("target_name", sa.String(length=40), nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=True),
        sa.Column("room_code", sa.String(length=8), nullable=True),
        sa.Column("reason", sa.String(length=16), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handled_by", sa.Integer(), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["handled_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_reports_target_id"), ["target_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_reports_club_id"), ["club_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_reports_status"), ["status"], unique=False)

    op.create_table(
        "mod_actions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(length=40), nullable=False),
        sa.Column("target_name", sa.String(length=40), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("mod_actions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_mod_actions_club_id"), ["club_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("mod_actions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_mod_actions_club_id"))
    op.drop_table("mod_actions")
    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_reports_status"))
        batch_op.drop_index(batch_op.f("ix_reports_club_id"))
        batch_op.drop_index(batch_op.f("ix_reports_target_id"))
    op.drop_table("reports")
    with op.batch_alter_table("blocks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_blocks_blocked_id"))
    op.drop_table("blocks")
    with op.batch_alter_table("memberships", schema=None) as batch_op:
        batch_op.drop_column("muted_until")
