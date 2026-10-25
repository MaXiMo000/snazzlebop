"""Fair play: games and battles remember which group of accounts played them, so the same group can't
keep earning from each other (fairplay.py).

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("results", "battles"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("group_key", sa.String(length=32), nullable=False, server_default="")
            )


def downgrade() -> None:
    for table in ("battles", "results"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column("group_key")
