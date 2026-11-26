"""Public tender market source and scan checkpoint.

Revision ID: tnd20261126market02
Revises: tnd20261126module01
"""

import sqlalchemy as sa
from alembic import op


revision = "tnd20261126market02"
down_revision = "tnd20261126module01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tender_market_publication",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("external_id", sa.String(300), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("canonical_url", sa.String(2048), nullable=True),
        sa.Column("title", sa.String(1000), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seen_generation", sa.Integer(), nullable=False),
        sa.Column("lot_snapshot", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_tender_market_native_identity"),
    )
    op.create_index("ix_tender_market_active_page", "tender_market_publication", ["active", "id"])
    checkpoint = op.create_table(
        "tender_market_checkpoint",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cursor", sa.String(2048), nullable=True),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(checkpoint, [{"id": 1, "generation": 1}])


def downgrade() -> None:
    op.drop_table("tender_market_checkpoint")
    op.drop_index("ix_tender_market_active_page", table_name="tender_market_publication")
    op.drop_table("tender_market_publication")
