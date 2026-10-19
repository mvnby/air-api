"""Add shared catalog reference documents and explicit inheritance.

Revision ID: cat20261019doc02
Revises: cat20261019acc01
"""

from alembic import op
import sqlalchemy as sa

revision = "cat20261019doc02"
down_revision = "cat20261019acc01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_document",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brand_id", sa.Integer(), nullable=True),
        sa.Column("series_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(24), nullable=False, server_default="other"),
        sa.Column("title", sa.String(250), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="public"),
        sa.Column("inherit_to_products", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["brand_id"], ["brand.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["series_id"], ["product_series.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "(CASE WHEN brand_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN series_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN product_id IS NULL THEN 0 ELSE 1 END) = 1",
            name="ck_catalog_document_one_owner",
        ),
        sa.CheckConstraint("visibility IN ('public', 'internal')", name="ck_catalog_document_visibility"),
        sa.CheckConstraint(
            "kind IN ('catalog', 'operation', 'installation', 'service', 'brochure', 'certificate', 'other')",
            name="ck_catalog_document_kind",
        ),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_catalog_document_title"),
        sa.CheckConstraint("year IS NULL OR year BETWEEN 1900 AND 2200", name="ck_catalog_document_year"),
        sa.UniqueConstraint("brand_id", "url", name="uq_catalog_document_brand_url"),
        sa.UniqueConstraint("series_id", "url", name="uq_catalog_document_series_url"),
        sa.UniqueConstraint("product_id", "url", name="uq_catalog_document_product_url"),
    )
    for owner in ("brand", "series", "product"):
        op.create_index(f"ix_catalog_document_{owner}_id", "catalog_document", [f"{owner}_id"])


def downgrade() -> None:
    op.drop_table("catalog_document")
