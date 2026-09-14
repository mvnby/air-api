"""Scope service catalogs and estimates by tenant.

Revision ID: e59b2c3d4e5f
Revises: e58a1b2c3d4
"""

from alembic import op
import sqlalchemy as sa


revision = "e59b2c3d4e5f"
down_revision = "e58a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("service", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.add_column("service", sa.Column("source_service_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_service_tenant", "service", "tenant", ["tenant_id"], ["id"])
    op.create_foreign_key(
        "fk_service_source",
        "service",
        "service",
        ["source_service_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_index("ix_service_slug", table_name="service")
    op.create_index("ix_service_slug", "service", ["slug"], unique=False)
    op.create_index("ix_service_tenant_id", "service", ["tenant_id"], unique=False)
    op.create_index(
        "ix_service_source_service_id",
        "service",
        ["source_service_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_service_tenant_slug",
        "service",
        ["tenant_id", "slug"],
    )
    op.create_index(
        "uq_service_canonical_slug",
        "service",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
        sqlite_where=sa.text("tenant_id IS NULL"),
    )
    op.create_index(
        "uq_service_tenant_source",
        "service",
        ["tenant_id", "source_service_id"],
        unique=True,
        postgresql_where=sa.text(
            "tenant_id IS NOT NULL AND source_service_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "tenant_id IS NOT NULL AND source_service_id IS NOT NULL"
        ),
    )

    op.add_column("service_tariff", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.add_column(
        "service_tariff",
        sa.Column("source_tariff_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_service_tariff_tenant",
        "service_tariff",
        "tenant",
        ["tenant_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_service_tariff_source",
        "service_tariff",
        "service_tariff",
        ["source_tariff_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_service_tariff_tenant_id",
        "service_tariff",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_service_tariff_source_tariff_id",
        "service_tariff",
        ["source_tariff_id"],
        unique=False,
    )
    op.create_index(
        "uq_service_tariff_tenant_source",
        "service_tariff",
        ["tenant_id", "source_tariff_id"],
        unique=True,
        postgresql_where=sa.text(
            "tenant_id IS NOT NULL AND source_tariff_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "tenant_id IS NOT NULL AND source_tariff_id IS NOT NULL"
        ),
    )

    op.add_column(
        "service_tariff_rule",
        sa.Column("source_rule_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_service_tariff_rule_source",
        "service_tariff_rule",
        "service_tariff_rule",
        ["source_rule_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_service_tariff_rule_source_rule_id",
        "service_tariff_rule",
        ["source_rule_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_service_tariff_rule_parent_source",
        "service_tariff_rule",
        ["tariff_id", "source_rule_id"],
    )

    op.add_column(
        "installation_rates",
        sa.Column("tenant_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "installation_rates",
        sa.Column("source_installation_rate_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_installation_rates_tenant",
        "installation_rates",
        "tenant",
        ["tenant_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_installation_rates_source",
        "installation_rates",
        "installation_rates",
        ["source_installation_rate_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_installation_rates_tenant_id",
        "installation_rates",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_installation_rates_source_installation_rate_id",
        "installation_rates",
        ["source_installation_rate_id"],
        unique=False,
    )
    op.create_index(
        "uq_installation_rate_tenant_source",
        "installation_rates",
        ["tenant_id", "source_installation_rate_id"],
        unique=True,
        postgresql_where=sa.text(
            "tenant_id IS NOT NULL AND source_installation_rate_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "tenant_id IS NOT NULL AND source_installation_rate_id IS NOT NULL"
        ),
    )

    op.add_column(
        "service_estimate",
        sa.Column("tenant_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_service_estimate_tenant",
        "service_estimate",
        "tenant",
        ["tenant_id"],
        ["id"],
    )
    op.create_index(
        "ix_service_estimate_tenant_id",
        "service_estimate",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_service_estimate_tenant_id", table_name="service_estimate")
    op.drop_constraint("fk_service_estimate_tenant", "service_estimate", type_="foreignkey")
    op.drop_column("service_estimate", "tenant_id")

    op.drop_index("uq_installation_rate_tenant_source", table_name="installation_rates")
    op.drop_index(
        "ix_installation_rates_source_installation_rate_id",
        table_name="installation_rates",
    )
    op.drop_index("ix_installation_rates_tenant_id", table_name="installation_rates")
    op.drop_constraint("fk_installation_rates_source", "installation_rates", type_="foreignkey")
    op.drop_constraint("fk_installation_rates_tenant", "installation_rates", type_="foreignkey")
    op.drop_column("installation_rates", "source_installation_rate_id")
    op.drop_column("installation_rates", "tenant_id")

    op.drop_constraint(
        "uq_service_tariff_rule_parent_source",
        "service_tariff_rule",
        type_="unique",
    )
    op.drop_index(
        "ix_service_tariff_rule_source_rule_id",
        table_name="service_tariff_rule",
    )
    op.drop_constraint(
        "fk_service_tariff_rule_source",
        "service_tariff_rule",
        type_="foreignkey",
    )
    op.drop_column("service_tariff_rule", "source_rule_id")

    op.drop_index("uq_service_tariff_tenant_source", table_name="service_tariff")
    op.drop_index("ix_service_tariff_source_tariff_id", table_name="service_tariff")
    op.drop_index("ix_service_tariff_tenant_id", table_name="service_tariff")
    op.drop_constraint("fk_service_tariff_source", "service_tariff", type_="foreignkey")
    op.drop_constraint("fk_service_tariff_tenant", "service_tariff", type_="foreignkey")
    op.drop_column("service_tariff", "source_tariff_id")
    op.drop_column("service_tariff", "tenant_id")

    op.drop_index("uq_service_tenant_source", table_name="service")
    op.drop_index("uq_service_canonical_slug", table_name="service")
    op.drop_constraint("uq_service_tenant_slug", "service", type_="unique")
    op.drop_index("ix_service_source_service_id", table_name="service")
    op.drop_index("ix_service_tenant_id", table_name="service")
    op.drop_index("ix_service_slug", table_name="service")
    op.create_index("ix_service_slug", "service", ["slug"], unique=True)
    op.drop_constraint("fk_service_source", "service", type_="foreignkey")
    op.drop_constraint("fk_service_tenant", "service", type_="foreignkey")
    op.drop_column("service", "source_service_id")
    op.drop_column("service", "tenant_id")
