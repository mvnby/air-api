"""Add a tenant-scoped register of installation material purchase prices."""

import sqlalchemy as sa
from alembic import op

revision = "inst20261126material01"
down_revision = "tnd20261126market03"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "installation_material_price",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("supplier", sa.String(120), nullable=False),
        sa.Column("unit", sa.String(8), nullable=False),
        sa.Column("pack_quantity", sa.Numeric(12, 4), nullable=False),
        sa.Column("pack_price_byn", sa.Numeric(12, 2), nullable=False),
        sa.Column("checked_on", sa.Date(), nullable=False),
        sa.Column("source_url", sa.String(2083)),
        sa.Column("note", sa.String(500), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id", "title", "supplier", name="uq_installation_material_price_item"),
        sa.CheckConstraint("pack_quantity > 0 AND pack_price_byn > 0", name="ck_installation_material_price_amounts"),
    )


def downgrade():
    op.drop_table("installation_material_price")
