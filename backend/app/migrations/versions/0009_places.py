"""Places: colleges and companies, the email domains that prove membership, who is verified where (by a
keyed hash of the address, never the address), pending codes, and requests for new places.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "places",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=48), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("places", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_places_slug"), ["slug"], unique=True)

    op.create_table(
        "place_domains",
        sa.Column("domain", sa.String(length=120), nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("domain"),
    )
    with op.batch_alter_table("place_domains", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_place_domains_place_id"), ["place_id"], unique=False)

    op.create_table(
        "user_places",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "place_id"),
        sa.UniqueConstraint("place_id", "email_hash"),
    )

    op.create_table(
        "place_codes",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "place_requests",
        sa.Column("domain", sa.String(length=120), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("last_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("domain"),
    )


def downgrade() -> None:
    op.drop_table("place_requests")
    op.drop_table("place_codes")
    op.drop_table("user_places")
    with op.batch_alter_table("place_domains", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_place_domains_place_id"))
    op.drop_table("place_domains")
    with op.batch_alter_table("places", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_places_slug"))
    op.drop_table("places")
