"""Add tenant-scoped Belzakupki import checkpoint.

Revision ID: e64f5a6b7c8d
Revises: e63f4a5b6c7d
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e64f5a6b7c8d"
down_revision: str | None = "e63f4a5b6c7d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "belzakupki_import_checkpoint",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("cursor", sa.String(length=2048), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_belzakupki_import_checkpoint_storefront_tenant",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "storefront_id",
            name="uq_belzakupki_import_checkpoint_scope",
        ),
    )
    op.create_index(
        "ix_belzakupki_import_checkpoint_tenant_id",
        "belzakupki_import_checkpoint",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_belzakupki_import_checkpoint_storefront_id",
        "belzakupki_import_checkpoint",
        ["storefront_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_belzakupki_import_checkpoint_storefront_id",
        table_name="belzakupki_import_checkpoint",
    )
    op.drop_index(
        "ix_belzakupki_import_checkpoint_tenant_id",
        table_name="belzakupki_import_checkpoint",
    )
    op.drop_table("belzakupki_import_checkpoint")
