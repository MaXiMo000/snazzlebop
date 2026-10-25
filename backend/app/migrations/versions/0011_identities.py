"""Identities: ways to sign in other than the password (Google, by its stable account id).

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "identities",
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("provider", "subject"),
    )
    with op.batch_alter_table("identities", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_identities_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("identities", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_identities_user_id"))
    op.drop_table("identities")
