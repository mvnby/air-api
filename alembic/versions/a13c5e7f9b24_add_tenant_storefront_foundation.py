"""Add tenant and storefront foundation.

Revision ID: a13c5e7f9b24
Revises: 9b4d6f8a1c30
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "a13c5e7f9b24"
down_revision: Union[str, Sequence[str], None] = "9b4d6f8a1c30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_tenant_status_valid"),
        sa.UniqueConstraint("slug", name="uq_tenant_slug"),
    )
    op.create_index("ix_tenant_kind", "tenant", ["kind"], unique=False)
    op.create_index("ix_tenant_status", "tenant", ["status"], unique=False)

    op.create_table(
        "tenant_membership",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("staff_user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'disabled')",
            name="ck_tenant_membership_status_valid",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["staff_user_id"], ["staff_users.id"]),
        sa.UniqueConstraint(
            "tenant_id",
            "staff_user_id",
            name="uq_tenant_membership_tenant_staff_user",
        ),
    )
    op.create_index("ix_tenant_membership_tenant_id", "tenant_membership", ["tenant_id"], unique=False)
    op.create_index("ix_tenant_membership_staff_user_id", "tenant_membership", ["staff_user_id"], unique=False)
    op.create_index("ix_tenant_membership_role", "tenant_membership", ["role"], unique=False)
    op.create_index("ix_tenant_membership_status", "tenant_membership", ["status"], unique=False)

    op.create_table(
        "storefront",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("default_locale", sa.String(length=16), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'disabled')",
            name="ck_storefront_status_valid",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_storefront_tenant_slug"),
    )
    op.create_index("ix_storefront_tenant_id", "storefront", ["tenant_id"], unique=False)
    op.create_index("ix_storefront_slug", "storefront", ["slug"], unique=False)
    op.create_index("ix_storefront_status", "storefront", ["status"], unique=False)
    op.create_index("ix_storefront_city", "storefront", ["city"], unique=False)
    op.create_index(
        "uq_storefront_default_per_tenant",
        "storefront",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
        sqlite_where=sa.text("is_default = 1"),
    )

    op.create_table(
        "storefront_domain",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("hostname", sa.String(length=253), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'disabled')",
            name="ck_storefront_domain_status_valid",
        ),
        sa.ForeignKeyConstraint(["storefront_id"], ["storefront.id"]),
        sa.UniqueConstraint("hostname", name="uq_storefront_domain_hostname"),
    )
    op.create_index("ix_storefront_domain_storefront_id", "storefront_domain", ["storefront_id"], unique=False)
    op.create_index("ix_storefront_domain_status", "storefront_domain", ["status"], unique=False)
    op.create_index(
        "uq_storefront_primary_domain",
        "storefront_domain",
        ["storefront_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
        sqlite_where=sa.text("is_primary = 1"),
    )

    now = datetime.now(timezone.utc)
    tenant_table = sa.table(
        "tenant",
        sa.column("slug", sa.String),
        sa.column("display_name", sa.String),
        sa.column("kind", sa.String),
        sa.column("status", sa.String),
        sa.column("is_system", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        tenant_table,
        [
            {
                "slug": "mvn",
                "display_name": "Мастер Воздуха",
                "kind": "operator",
                "status": "active",
                "is_system": True,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )

    connection = op.get_bind()
    tenant_id = connection.execute(sa.text("SELECT id FROM tenant WHERE slug = 'mvn'")).scalar_one()
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
            """
        ),
        {
            "tenant_id": tenant_id,
            "created_at": now,
            "updated_at": now,
        },
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO storefront (
                tenant_id, slug, display_name, status, city, default_locale,
                currency, is_default, created_at, updated_at
            ) VALUES (
                :tenant_id, 'main', 'MVN', 'active', 'Витебск', 'ru-BY',
                'BYN', :is_default, :created_at, :updated_at
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "is_default": True,
            "created_at": now,
            "updated_at": now,
        },
    )
    storefront_id = connection.execute(
        sa.text("SELECT id FROM storefront WHERE tenant_id = :tenant_id AND slug = 'main'"),
        {"tenant_id": tenant_id},
    ).scalar_one()

    domain_table = sa.table(
        "storefront_domain",
        sa.column("storefront_id", sa.Integer),
        sa.column("hostname", sa.String),
        sa.column("status", sa.String),
        sa.column("is_primary", sa.Boolean),
        sa.column("verified_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        domain_table,
        [
            {
                "storefront_id": storefront_id,
                "hostname": "mvn.by",
                "status": "active",
                "is_primary": True,
                "verified_at": now,
                "created_at": now,
                "updated_at": now,
            },
            {
                "storefront_id": storefront_id,
                "hostname": "www.mvn.by",
                "status": "active",
                "is_primary": False,
                "verified_at": now,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("uq_storefront_primary_domain", table_name="storefront_domain")
    op.drop_index("ix_storefront_domain_status", table_name="storefront_domain")
    op.drop_index("ix_storefront_domain_storefront_id", table_name="storefront_domain")
    op.drop_table("storefront_domain")

    op.drop_index("uq_storefront_default_per_tenant", table_name="storefront")
    op.drop_index("ix_storefront_city", table_name="storefront")
    op.drop_index("ix_storefront_status", table_name="storefront")
    op.drop_index("ix_storefront_slug", table_name="storefront")
    op.drop_index("ix_storefront_tenant_id", table_name="storefront")
    op.drop_table("storefront")

    op.drop_index("ix_tenant_membership_status", table_name="tenant_membership")
    op.drop_index("ix_tenant_membership_role", table_name="tenant_membership")
    op.drop_index("ix_tenant_membership_staff_user_id", table_name="tenant_membership")
    op.drop_index("ix_tenant_membership_tenant_id", table_name="tenant_membership")
    op.drop_table("tenant_membership")

    op.drop_index("ix_tenant_status", table_name="tenant")
    op.drop_index("ix_tenant_kind", table_name="tenant")
    op.drop_table("tenant")
