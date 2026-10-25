"""The coin ledger: every change to a balance as an append-only row. Existing balances become one
opening row each, so the ledger and users.coins agree from the start.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=24), nullable=False),
        sa.Column("ref_type", sa.String(length=16), nullable=False),
        sa.Column("ref_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "reason", "ref_type", "ref_id"),
    )
    with op.batch_alter_table("ledger", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_ledger_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_ledger_user_id"), ["user_id"], unique=False)
    op.execute(
        "INSERT INTO ledger (user_id, currency, delta, reason, ref_type, ref_id, created_at) "
        "SELECT id, 'coins', coins, 'opening', 'account', CAST(id AS VARCHAR(64)), CURRENT_TIMESTAMP "
        "FROM users WHERE coins <> 0"
    )


def downgrade() -> None:
    with op.batch_alter_table("ledger", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ledger_user_id"))
        batch_op.drop_index(batch_op.f("ix_ledger_created_at"))
    op.drop_table("ledger")
