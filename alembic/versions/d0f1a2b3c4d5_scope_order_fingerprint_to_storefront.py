"""scope order source fingerprint uniqueness to the exact storefront

Revision ID: d0f1a2b3c4d5
Revises: c9e0f1a2b3d4
Create Date: 2026-08-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "d0f1a2b3c4d5"
down_revision = "c9e0f1a2b3d4"
branch_labels = None
depends_on = None


ORDER_FINGERPRINT_INDEX = "uq_order_source_fingerprint"


def _assert_no_null_provenance() -> None:
    count = int(
        op.get_bind()
        .execute(
            sa.text(
                'SELECT COUNT(*) FROM "order" '
                "WHERE source_fingerprint IS NOT NULL "
                "AND (tenant_id IS NULL OR storefront_id IS NULL)"
            )
        )
        .scalar_one()
        or 0
    )
    if count:
        raise RuntimeError(
            "Refusing storefront idempotency upgrade: "
            f"order_fingerprint_null_scope={count}"
        )


def _assert_downgrade_is_lossless() -> None:
    count = int(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT COUNT(*) FROM ("
                'SELECT tenant_id, source_fingerprint FROM "order" '
                "WHERE source_fingerprint IS NOT NULL "
                "GROUP BY tenant_id, source_fingerprint HAVING COUNT(*) > 1"
                ") AS duplicates"
            )
        )
        .scalar_one()
        or 0
    )
    if count:
        raise RuntimeError(
            "Refusing storefront idempotency downgrade: "
            f"duplicate_tenant_order_fingerprint={count}"
        )


def _create_storefront_scoped_index() -> None:
    op.create_index(
        ORDER_FINGERPRINT_INDEX,
        "order",
        ["tenant_id", "storefront_id", "source_fingerprint"],
        unique=True,
        postgresql_where=sa.text("source_fingerprint IS NOT NULL"),
        sqlite_where=sa.text("source_fingerprint IS NOT NULL"),
    )


def _create_tenant_scoped_index() -> None:
    op.create_index(
        ORDER_FINGERPRINT_INDEX,
        "order",
        ["tenant_id", "source_fingerprint"],
        unique=True,
        postgresql_where=sa.text("source_fingerprint IS NOT NULL"),
        sqlite_where=sa.text("source_fingerprint IS NOT NULL"),
    )


def upgrade() -> None:
    _assert_no_null_provenance()
    op.drop_index(ORDER_FINGERPRINT_INDEX, table_name="order")
    _create_storefront_scoped_index()


def downgrade() -> None:
    _assert_downgrade_is_lossless()
    op.drop_index(ORDER_FINGERPRINT_INDEX, table_name="order")
    _create_tenant_scoped_index()
