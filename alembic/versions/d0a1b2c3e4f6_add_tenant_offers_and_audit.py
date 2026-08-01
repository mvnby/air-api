"""Add tenant-owned storefront offers and audit events.

Revision ID: d0a1b2c3e4f6
Revises: d0f1a2b3c4d5
Create Date: 2026-07-31
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d0a1b2c3e4f6"
down_revision: str | Sequence[str] | None = "d0f1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_offer",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("old_price", sa.Integer(), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_by_username", sa.String(length=160), nullable=False),
        sa.Column("updated_by_username", sa.String(length=160), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("price >= 0", name="ck_tenant_offer_price_non_negative"),
        sa.CheckConstraint(
            "old_price IS NULL OR old_price >= price",
            name="ck_tenant_offer_old_price_valid",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_tenant_offer_status_valid",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_tenant_offer_storefront_tenant",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "storefront_id",
            "product_id",
            name="uq_tenant_offer_scope_product",
        ),
    )
    op.create_index(
        "ix_tenant_offer_product_id",
        "tenant_offer",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        "ix_tenant_offer_scope_visibility",
        "tenant_offer",
        ["tenant_id", "storefront_id", "status", "is_published"],
        unique=False,
    )

    op.create_table(
        "tenant_audit_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("actor_staff_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_username", sa.String(length=160), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("change_set", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_tenant_audit_storefront_tenant",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tenant_audit_scope_created_at",
        "tenant_audit_event",
        ["tenant_id", "storefront_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_tenant_audit_scope_entity",
        "tenant_audit_event",
        ["tenant_id", "storefront_id", "entity_type", "entity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tenant_audit_scope_entity",
        table_name="tenant_audit_event",
    )
    op.drop_index(
        "ix_tenant_audit_scope_created_at",
        table_name="tenant_audit_event",
    )
    op.drop_table("tenant_audit_event")
    op.drop_index(
        "ix_tenant_offer_scope_visibility",
        table_name="tenant_offer",
    )
    op.drop_index("ix_tenant_offer_product_id", table_name="tenant_offer")
    op.drop_table("tenant_offer")
