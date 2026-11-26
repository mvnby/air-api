"""Durable receipt and lease for verification of public tender originals.

Revision ID: tnd20261126market03
Revises: tnd20261126market02
"""

import sqlalchemy as sa
from alembic import op


revision = "tnd20261126market03"
down_revision = "tnd20261126market02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_tender_market_canonical_active", "tender_market_publication", ["canonical_url", "active", "id"])
    op.create_table(
        "tender_market_evidence",
        sa.Column("publication_id", sa.Integer(), nullable=False),
        sa.Column("source_revision", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reader_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.String(32)),
        sa.Column("checked_at", sa.DateTime(timezone=True)),
        sa.Column("fingerprint", sa.String(64)),
        sa.Column("documents_source_url", sa.String(2048)),
        sa.Column("report", sa.JSON()),
        sa.Column("error", sa.String(300)),
        sa.ForeignKeyConstraint(["publication_id"], ["tender_market_publication.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("publication_id"),
        sa.CheckConstraint("status IN ('queued', 'reading', 'completed', 'failed')", name="ck_tender_market_evidence_status"),
    )
    op.create_index("ix_tender_market_evidence_queue", "tender_market_evidence", ["status", "available_at"])


def downgrade() -> None:
    op.drop_index("ix_tender_market_evidence_queue", table_name="tender_market_evidence")
    op.drop_table("tender_market_evidence")
    op.drop_index("ix_tender_market_canonical_active", table_name="tender_market_publication")
