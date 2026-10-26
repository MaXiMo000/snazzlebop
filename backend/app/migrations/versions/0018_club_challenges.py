"""Club challenges: room activity remembers which club's room it happened in.

Revision ID: 0018
Revises: 0017
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("activity", schema=None) as batch_op:
        batch_op.add_column(sa.Column("club_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_activity_club_id"), ["club_id"], unique=False)
        batch_op.create_foreign_key("fk_activity_club_id", "clubs", ["club_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("activity", schema=None) as batch_op:
        batch_op.drop_constraint("fk_activity_club_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_activity_club_id"))
        batch_op.drop_column("club_id")
