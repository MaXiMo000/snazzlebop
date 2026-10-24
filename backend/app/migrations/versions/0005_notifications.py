"""Notifications: the inbox, browsers subscribed to pushes, and each person's notification settings.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.String(length=240), nullable=False),
        sa.Column("link", sa.String(length=200), nullable=False),
        sa.Column("group_key", sa.String(length=80), nullable=True),
        sa.Column("pushed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_notifications_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_notifications_created_at"), ["created_at"], unique=False)

    op.create_table(
        "push_subs",
        sa.Column("endpoint", sa.String(length=1000), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("p256dh", sa.String(length=120), nullable=False),
        sa.Column("auth", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("endpoint"),
    )
    with op.batch_alter_table("push_subs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_push_subs_user_id"), ["user_id"], unique=False)

    op.create_table(
        "user_prefs",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_prefs")
    with op.batch_alter_table("push_subs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_push_subs_user_id"))
    op.drop_table("push_subs")
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notifications_created_at"))
        batch_op.drop_index(batch_op.f("ix_notifications_user_id"))
    op.drop_table("notifications")
