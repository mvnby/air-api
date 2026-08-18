"""add system-owned shared catalog grants

Revision ID: a6b7c8d9e0f1
Revises: f5c6d7e8a9b0
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "a6b7c8d9e0f1"
down_revision: str | None = "f5c6d7e8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_catalog_grant",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("price_policy", sa.String(length=32), nullable=False),
        sa.Column("owner_type", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_by_username", sa.String(length=160), nullable=False),
        sa.Column("updated_by_username", sa.String(length=160), nullable=False),
        sa.Column("last_completed_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_completed_sync_fingerprint",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mode IN ('all_published')",
            name="ck_tenant_catalog_grant_mode_valid",
        ),
        sa.CheckConstraint(
            "price_policy IN ('inherit_master')",
            name="ck_tenant_catalog_grant_price_policy_valid",
        ),
        sa.CheckConstraint(
            "owner_type IN ('system')",
            name="ck_tenant_catalog_grant_owner_type_valid",
        ),
        sa.CheckConstraint(
            "status IN ('syncing', 'active', 'disabled')",
            name="ck_tenant_catalog_grant_status_valid",
        ),
        sa.CheckConstraint(
            "revision > 0",
            name="ck_tenant_catalog_grant_revision_positive",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
        ),
        sa.ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_tenant_catalog_grant_storefront_tenant",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "storefront_id",
            name="uq_tenant_catalog_grant_id_scope",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "storefront_id",
            name="uq_tenant_catalog_grant_scope",
        ),
    )
    op.add_column(
        "tenant_offer",
        sa.Column("catalog_grant_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tenant_offer",
        sa.Column(
            "price_source",
            sa.String(length=32),
            server_default="manual",
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_tenant_offer_catalog_grant_id"),
        "tenant_offer",
        ["catalog_grant_id"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_tenant_offer_price_source_valid",
        "tenant_offer",
        "price_source IN ('manual', 'inherited_master')",
    )
    op.create_check_constraint(
        "ck_tenant_offer_inherited_price_has_grant",
        "tenant_offer",
        "price_source = 'manual' OR catalog_grant_id IS NOT NULL",
    )
    op.create_foreign_key(
        "fk_tenant_offer_catalog_grant_scope",
        "tenant_offer",
        "tenant_catalog_grant",
        ["catalog_grant_id", "tenant_id", "storefront_id"],
        ["id", "tenant_id", "storefront_id"],
    )


def downgrade() -> None:
    # A downgrade must fail closed: materialized grant offers must not become
    # ordinary visible offers after their ownership metadata is removed.
    op.execute(
        "UPDATE tenant_offer SET status = 'disabled', is_published = false "
        "WHERE catalog_grant_id IS NOT NULL"
    )
    op.drop_constraint(
        "fk_tenant_offer_catalog_grant_scope",
        "tenant_offer",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_tenant_offer_inherited_price_has_grant",
        "tenant_offer",
        type_="check",
    )
    op.drop_constraint(
        "ck_tenant_offer_price_source_valid",
        "tenant_offer",
        type_="check",
    )
    op.drop_index(
        op.f("ix_tenant_offer_catalog_grant_id"),
        table_name="tenant_offer",
    )
    op.drop_column("tenant_offer", "price_source")
    op.drop_column("tenant_offer", "catalog_grant_id")
    op.drop_table("tenant_catalog_grant")
