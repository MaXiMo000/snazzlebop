"""Platform staff: account suspensions, and which report cases staff own.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("suspended_until", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("suspend_reason", sa.String(length=200), nullable=False, server_default="")
        )

    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.add_column(sa.Column("staff", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_reports_staff"), ["staff"], unique=False)

    # Cases staff already own: escalated ones, and reports that aren't about a club.
    reports = sa.table(
        "reports",
        sa.column("staff", sa.Boolean),
        sa.column("club_id", sa.Integer),
        sa.column("status", sa.String),
    )
    op.get_bind().execute(
        reports.update()
        .where(sa.or_(reports.c.club_id.is_(None), reports.c.status == "escalated"))
        .values(staff=True)
    )


def downgrade() -> None:
    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_reports_staff"))
        batch_op.drop_column("staff")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("suspend_reason")
        batch_op.drop_column("suspended_until")
