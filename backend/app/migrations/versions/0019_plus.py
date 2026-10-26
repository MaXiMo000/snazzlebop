"""Snazzlebop Plus: the account's Plus end date, its subscriptions at Paddle, and handled webhooks.

Revision ID: 0019
Revises: 0018
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("plus_until", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("subscriptions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_subscriptions_user_id"), ["user_id"], unique=False)
    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=48), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("billing_events")
    with op.batch_alter_table("subscriptions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_subscriptions_user_id"))
    op.drop_table("subscriptions")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("plus_until")
