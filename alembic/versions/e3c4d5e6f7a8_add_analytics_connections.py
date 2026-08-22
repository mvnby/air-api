"""add storefront analytics connections

Revision ID: e3c4d5e6f7a8
Revises: d2b3c4d5e6f7
Create Date: 2026-08-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "d2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analytics_connection",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("public_config", sa.JSON(), nullable=False),
        sa.Column("encrypted_credentials", sa.Text(), nullable=False),
        sa.Column("credentials_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_analytics_connection_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_analytics_connection_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_analytics_connection_storefront_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "storefront_id",
            "provider",
            name="uq_analytics_connection_scope_provider",
        ),
    )
    op.create_index(
        "ix_analytics_connection_scope",
        "analytics_connection",
        ["tenant_id", "storefront_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_connection_scope", table_name="analytics_connection")
    op.drop_table("analytics_connection")
