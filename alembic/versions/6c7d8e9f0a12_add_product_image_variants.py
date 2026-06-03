"""add product image variants

Revision ID: 6c7d8e9f0a12
Revises: 5a6b7c8d9e10
Create Date: 2026-06-03 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "6c7d8e9f0a12"
down_revision: Union[str, Sequence[str], None] = "5a6b7c8d9e10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_image_variant",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_image_id", sa.Integer(), nullable=False),
        sa.Column("variant_type", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("storage_provider", sa.String(), nullable=False, server_default="local"),
        sa.Column("processing_status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("processing_stage", sa.String(), nullable=False, server_default="original_ingest"),
        sa.Column("processing_provider", sa.String(), nullable=True),
        sa.Column("manual_quality_status", sa.String(), nullable=False, server_default="unreviewed"),
        sa.Column("content_hash", sa.String(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("processing_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["product_image_id"], ["product_image.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_image_id",
            "variant_type",
            name="uq_product_image_variant_image_type",
        ),
    )
    op.create_index(
        "ix_product_image_variant_product_image_id",
        "product_image_variant",
        ["product_image_id"],
        unique=False,
    )
    op.create_index(
        "ix_product_image_variant_variant_type",
        "product_image_variant",
        ["variant_type"],
        unique=False,
    )
    op.create_index(
        "ix_product_image_variant_storage_provider",
        "product_image_variant",
        ["storage_provider"],
        unique=False,
    )
    op.create_index(
        "ix_product_image_variant_processing_status",
        "product_image_variant",
        ["processing_status"],
        unique=False,
    )
    op.create_index(
        "ix_product_image_variant_processing_stage",
        "product_image_variant",
        ["processing_stage"],
        unique=False,
    )
    op.create_index(
        "ix_product_image_variant_processing_provider",
        "product_image_variant",
        ["processing_provider"],
        unique=False,
    )
    op.create_index(
        "ix_product_image_variant_manual_quality_status",
        "product_image_variant",
        ["manual_quality_status"],
        unique=False,
    )
    op.create_index(
        "ix_product_image_variant_content_hash",
        "product_image_variant",
        ["content_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_product_image_variant_content_hash", table_name="product_image_variant")
    op.drop_index(
        "ix_product_image_variant_manual_quality_status",
        table_name="product_image_variant",
    )
    op.drop_index(
        "ix_product_image_variant_processing_provider",
        table_name="product_image_variant",
    )
    op.drop_index(
        "ix_product_image_variant_processing_stage",
        table_name="product_image_variant",
    )
    op.drop_index(
        "ix_product_image_variant_processing_status",
        table_name="product_image_variant",
    )
    op.drop_index("ix_product_image_variant_storage_provider", table_name="product_image_variant")
    op.drop_index("ix_product_image_variant_variant_type", table_name="product_image_variant")
    op.drop_index(
        "ix_product_image_variant_product_image_id",
        table_name="product_image_variant",
    )
    op.drop_table("product_image_variant")
