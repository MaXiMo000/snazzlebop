"""Reports as cases: a public id, priority, assignee, external ticket links and triage notes on each
report, a timeline per report, and the outbox that delivers events to other systems.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

import secrets

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.add_column(sa.Column("public_id", sa.String(length=24), nullable=True))
        batch_op.add_column(
            sa.Column("priority", sa.String(length=8), nullable=False, server_default="normal")
        )
        batch_op.add_column(sa.Column("assignee", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("external", sa.JSON(), nullable=False, server_default="{}"))
        batch_op.add_column(sa.Column("triage", sa.JSON(), nullable=False, server_default="{}"))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))

    # Reports filed before this get their public id now.
    bind = op.get_bind()
    reports = sa.table("reports", sa.column("id", sa.Integer), sa.column("public_id", sa.String))
    for (report_id,) in bind.execute(sa.select(reports.c.id)).all():
        bind.execute(
            reports.update()
            .where(reports.c.id == report_id)
            .values(public_id=f"rpt_{secrets.token_urlsafe(9)}")
        )

    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.alter_column("public_id", existing_type=sa.String(length=24), nullable=False)
        batch_op.create_index(batch_op.f("ix_reports_public_id"), ["public_id"], unique=True)

    op.create_table(
        "report_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("actor", sa.String(length=80), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("report_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_report_events_report_id"), ["report_id"], unique=False)

    op.create_table(
        "outbox",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sink", sa.String(length=24), nullable=False),
        sa.Column("topic", sa.String(length=40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("outbox", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_outbox_next_at"), ["next_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("outbox", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_outbox_next_at"))
    op.drop_table("outbox")
    with op.batch_alter_table("report_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_report_events_report_id"))
    op.drop_table("report_events")
    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_reports_public_id"))
        batch_op.drop_column("updated_at")
        batch_op.drop_column("triage")
        batch_op.drop_column("external")
        batch_op.drop_column("assignee")
        batch_op.drop_column("priority")
        batch_op.drop_column("public_id")
