"""Account email: an optional address on each account, emailed links (hashed, single use) and the
browsers each account has signed in from.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(length=254), nullable=True))
        batch_op.add_column(
            sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_email"), ["email"], unique=False)

    op.create_table(
        "email_tokens",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=8), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    with op.batch_alter_table("email_tokens", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_email_tokens_user_id"), ["user_id"], unique=False)

    op.create_table(
        "known_devices",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("device_hash", sa.String(length=64), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "device_hash"),
    )


def downgrade() -> None:
    op.drop_table("known_devices")
    with op.batch_alter_table("email_tokens", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_email_tokens_user_id"))
    op.drop_table("email_tokens")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_email"))
        batch_op.drop_column("email_verified")
        batch_op.drop_column("email")
