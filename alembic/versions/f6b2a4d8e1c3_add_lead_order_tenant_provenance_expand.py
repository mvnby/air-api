"""Expand lead and order provenance with nullable tenant/storefront keys.

Revision ID: f6b2a4d8e1c3
Revises: e9a1b2c3d4e5
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6b2a4d8e1c3"
down_revision: Union[str, Sequence[str], None] = "e9a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEAD_TENANT_FK = "fk_lead_tenant_id_tenant"
LEAD_STOREFRONT_FK = "fk_lead_storefront_id_storefront"
ORDER_TENANT_FK = "fk_order_tenant_id_tenant"
ORDER_STOREFRONT_FK = "fk_order_storefront_id_storefront"


def _expand_table(
    table_name: str,
    *,
    tenant_fk_name: str,
    storefront_fk_name: str,
) -> None:
    op.add_column(table_name, sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.add_column(table_name, sa.Column("storefront_id", sa.Integer(), nullable=True))

    # SQLite cannot add named constraints without rebuilding the parent table.
    # Rebuilding "order" breaks when child tables reference it with FK checks
    # enabled, so the local/test dialect keeps this expand step additive only.
    # PostgreSQL, the production dialect, gets both constraints in place.
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(tenant_fk_name, table_name, "tenant", ["tenant_id"], ["id"])
        op.create_foreign_key(
            storefront_fk_name,
            table_name,
            "storefront",
            ["storefront_id"],
            ["id"],
        )


def _downgrade_table(
    table_name: str,
    *,
    tenant_fk_name: str,
    storefront_fk_name: str,
) -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint(storefront_fk_name, table_name, type_="foreignkey")
        op.drop_constraint(tenant_fk_name, table_name, type_="foreignkey")
    op.drop_column(table_name, "storefront_id")
    op.drop_column(table_name, "tenant_id")


def upgrade() -> None:
    _expand_table(
        "lead",
        tenant_fk_name=LEAD_TENANT_FK,
        storefront_fk_name=LEAD_STOREFRONT_FK,
    )
    _expand_table(
        "order",
        tenant_fk_name=ORDER_TENANT_FK,
        storefront_fk_name=ORDER_STOREFRONT_FK,
    )
    op.create_index("ix_lead_tenant_status_created_at", "lead", ["tenant_id", "status", "created_at"])
    op.create_index("ix_lead_storefront_status_created_at", "lead", ["storefront_id", "status", "created_at"])
    op.create_index("ix_order_tenant_status_created_at", "order", ["tenant_id", "status", "created_at"])
    op.create_index("ix_order_storefront_status_created_at", "order", ["storefront_id", "status", "created_at"])


def downgrade() -> None:
    connection = op.get_bind()
    for table_name in ("lead", "order"):
        scoped_rows = connection.execute(
            sa.text(
                f'SELECT COUNT(*) FROM "{table_name}" '
                "WHERE tenant_id IS NOT NULL OR storefront_id IS NOT NULL"
            )
        ).scalar_one()
        if scoped_rows:
            raise RuntimeError(
                "Refusing to drop tenant provenance columns while scoped "
                f"{table_name} rows exist; roll the application forward instead"
            )

    op.drop_index("ix_order_storefront_status_created_at", table_name="order")
    op.drop_index("ix_order_tenant_status_created_at", table_name="order")
    op.drop_index("ix_lead_storefront_status_created_at", table_name="lead")
    op.drop_index("ix_lead_tenant_status_created_at", table_name="lead")
    _downgrade_table(
        "order",
        tenant_fk_name=ORDER_TENANT_FK,
        storefront_fk_name=ORDER_STOREFRONT_FK,
    )
    _downgrade_table(
        "lead",
        tenant_fk_name=LEAD_TENANT_FK,
        storefront_fk_name=LEAD_STOREFRONT_FK,
    )
