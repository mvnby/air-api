"""Expand Customer ownership and refresh system tenant memberships.

Revision ID: b8d9e0f1a2c3
Revises: a7c8d9e0f1b2
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8d9e0f1a2c3"
down_revision: Union[str, Sequence[str], None] = "a7c8d9e0f1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CUSTOMER_TENANT_FK = "fk_customer_tenant_id_tenant"
RECOGNITION_TENANT_FK = (
    "fk_customer_requisites_recognition_tenant_id_tenant"
)


def _add_tenant_column(table_name: str, *, constraint_name: str) -> None:
    op.add_column(table_name, sa.Column("tenant_id", sa.Integer(), nullable=True))
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            constraint_name,
            table_name,
            "tenant",
            ["tenant_id"],
            ["id"],
        )


def _drop_tenant_column(table_name: str, *, constraint_name: str) -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint(constraint_name, table_name, type_="foreignkey")
    op.drop_column(table_name, "tenant_id")


def _backfill_missing_system_memberships() -> None:
    connection = op.get_bind()
    tenant_id = connection.execute(
        sa.text(
            "SELECT id FROM tenant "
            "WHERE slug = 'mvn' AND is_system = :is_system"
        ),
        {"is_system": True},
    ).scalar_one()
    now = datetime.now(timezone.utc)
    connection.execute(
        sa.text(
            """
            INSERT INTO tenant_membership (
                tenant_id, staff_user_id, role, status, created_at, updated_at
            )
            SELECT
                :tenant_id,
                staff.id,
                COALESCE(NULLIF(TRIM(staff.primary_role), ''), 'installer'),
                CASE WHEN staff.status = 'active' THEN 'active' ELSE 'disabled' END,
                :created_at,
                :updated_at
            FROM staff_users AS staff
            WHERE NOT EXISTS (
                SELECT 1
                FROM tenant_membership AS membership
                WHERE membership.tenant_id = :tenant_id
                  AND membership.staff_user_id = staff.id
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "created_at": now,
            "updated_at": now,
        },
    )


def upgrade() -> None:
    _add_tenant_column("customer", constraint_name=CUSTOMER_TENANT_FK)
    _add_tenant_column(
        "customer_requisites_recognition",
        constraint_name=RECOGNITION_TENANT_FK,
    )
    op.create_index(
        "ix_customer_tenant_created_at",
        "customer",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_customer_tenant_phone",
        "customer",
        ["tenant_id", "phone"],
    )
    op.create_index(
        "ix_customer_tenant_inn",
        "customer",
        ["tenant_id", "inn"],
    )
    op.create_index(
        "ix_customer_requisites_tenant_created_at",
        "customer_requisites_recognition",
        ["tenant_id", "created_at"],
    )
    _backfill_missing_system_memberships()


def downgrade() -> None:
    connection = op.get_bind()
    for table_name in ("customer", "customer_requisites_recognition"):
        scoped_rows = connection.execute(
            sa.text(
                f'SELECT COUNT(*) FROM "{table_name}" '
                "WHERE tenant_id IS NOT NULL"
            )
        ).scalar_one()
        if scoped_rows:
            raise RuntimeError(
                "Refusing to drop tenant ownership while scoped "
                f"{table_name} rows exist; roll the application forward instead"
            )

    op.drop_index(
        "ix_customer_requisites_tenant_created_at",
        table_name="customer_requisites_recognition",
    )
    op.drop_index("ix_customer_tenant_inn", table_name="customer")
    op.drop_index("ix_customer_tenant_phone", table_name="customer")
    op.drop_index("ix_customer_tenant_created_at", table_name="customer")
    _drop_tenant_column(
        "customer_requisites_recognition",
        constraint_name=RECOGNITION_TENANT_FK,
    )
    _drop_tenant_column("customer", constraint_name=CUSTOMER_TENANT_FK)
