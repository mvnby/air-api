"""Add exact-storefront catalog revisions.

Revision ID: e1f2a3b4c5d6
Revises: d0a1b2c3e4f6
Create Date: 2026-08-01
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "d0a1b2c3e4f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "storefront_catalog_revision",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column(
            "revision",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision >= 0",
            name="ck_storefront_catalog_revision_non_negative",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_storefront_catalog_revision_storefront_tenant",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "storefront_id"),
    )
    op.create_index(
        "ix_integration_outbox_event_catalog_claim",
        "integration_outbox_event",
        [
            "event_type",
            "status",
            "available_at",
            "priority",
            "occurred_at",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_integration_outbox_event_catalog_claim",
        table_name="integration_outbox_event",
    )
    op.drop_table("storefront_catalog_revision")
