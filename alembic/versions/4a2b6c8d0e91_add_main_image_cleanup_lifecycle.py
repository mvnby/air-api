"""add main image cleanup lifecycle

Revision ID: 4a2b6c8d0e91
Revises: 8c4d2b6f1a90
Create Date: 2026-06-06 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "4a2b6c8d0e91"
down_revision: Union[str, Sequence[str], None] = "8c4d2b6f1a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_main_image_cleanup_batch",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="processing"),
        sa.Column("requested_limit", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("processor_method", sa.String(), nullable=False, server_default="noop"),
        sa.Column("processor_version", sa.String(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_main_image_cleanup_batch_status",
        "product_main_image_cleanup_batch",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_product_main_image_cleanup_batch_processor_method",
        "product_main_image_cleanup_batch",
        ["processor_method"],
        unique=False,
    )
    op.create_index(
        "ix_product_main_image_cleanup_batch_processor_version",
        "product_main_image_cleanup_batch",
        ["processor_version"],
        unique=False,
    )
    op.create_index(
        "ix_product_main_image_cleanup_batch_created_by",
        "product_main_image_cleanup_batch",
        ["created_by"],
        unique=False,
    )

    op.create_table(
        "product_main_image_cleanup_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("source_product_image_id", sa.Integer(), nullable=True),
        sa.Column("original_image_url", sa.String(), nullable=False),
        sa.Column("candidate_image_url", sa.String(), nullable=True),
        sa.Column("approved_image_url", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("skip_reason", sa.String(), nullable=True),
        sa.Column("reject_reason", sa.String(), nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("processor_method", sa.String(), nullable=True),
        sa.Column("processor_version", sa.String(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("candidate_storage_provider", sa.String(), nullable=True),
        sa.Column("candidate_content_hash", sa.String(), nullable=True),
        sa.Column("candidate_width", sa.Integer(), nullable=True),
        sa.Column("candidate_height", sa.Integer(), nullable=True),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["product_main_image_cleanup_batch.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_product_image_id"],
            ["product_image.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id",
            "original_image_url",
            name="uq_main_image_cleanup_product_original",
        ),
    )
    op.create_index(
        "ix_product_main_image_cleanup_item_batch_id",
        "product_main_image_cleanup_item",
        ["batch_id"],
        unique=False,
    )
    op.create_index(
        "ix_product_main_image_cleanup_item_product_id",
        "product_main_image_cleanup_item",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        "ix_product_main_image_cleanup_item_source_product_image_id",
        "product_main_image_cleanup_item",
        ["source_product_image_id"],
        unique=False,
    )
    op.create_index(
        "ix_product_main_image_cleanup_item_original_image_url",
        "product_main_image_cleanup_item",
        ["original_image_url"],
        unique=False,
    )
    op.create_index(
        "ix_product_main_image_cleanup_item_status",
        "product_main_image_cleanup_item",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_product_main_image_cleanup_item_processor_method",
        "product_main_image_cleanup_item",
        ["processor_method"],
        unique=False,
    )
    op.create_index(
        "ix_product_main_image_cleanup_item_processor_version",
        "product_main_image_cleanup_item",
        ["processor_version"],
        unique=False,
    )
    op.create_index(
        "ix_product_main_image_cleanup_item_candidate_storage_provider",
        "product_main_image_cleanup_item",
        ["candidate_storage_provider"],
        unique=False,
    )
    op.create_index(
        "ix_product_main_image_cleanup_item_candidate_content_hash",
        "product_main_image_cleanup_item",
        ["candidate_content_hash"],
        unique=False,
    )
    op.create_index(
        "ix_product_main_image_cleanup_item_approved_by",
        "product_main_image_cleanup_item",
        ["approved_by"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_product_main_image_cleanup_item_approved_by",
        table_name="product_main_image_cleanup_item",
    )
    op.drop_index(
        "ix_product_main_image_cleanup_item_candidate_content_hash",
        table_name="product_main_image_cleanup_item",
    )
    op.drop_index(
        "ix_product_main_image_cleanup_item_candidate_storage_provider",
        table_name="product_main_image_cleanup_item",
    )
    op.drop_index(
        "ix_product_main_image_cleanup_item_processor_version",
        table_name="product_main_image_cleanup_item",
    )
    op.drop_index(
        "ix_product_main_image_cleanup_item_processor_method",
        table_name="product_main_image_cleanup_item",
    )
    op.drop_index(
        "ix_product_main_image_cleanup_item_status",
        table_name="product_main_image_cleanup_item",
    )
    op.drop_index(
        "ix_product_main_image_cleanup_item_original_image_url",
        table_name="product_main_image_cleanup_item",
    )
    op.drop_index(
        "ix_product_main_image_cleanup_item_source_product_image_id",
        table_name="product_main_image_cleanup_item",
    )
    op.drop_index(
        "ix_product_main_image_cleanup_item_product_id",
        table_name="product_main_image_cleanup_item",
    )
    op.drop_index(
        "ix_product_main_image_cleanup_item_batch_id",
        table_name="product_main_image_cleanup_item",
    )
    op.drop_table("product_main_image_cleanup_item")
    op.drop_index(
        "ix_product_main_image_cleanup_batch_created_by",
        table_name="product_main_image_cleanup_batch",
    )
    op.drop_index(
        "ix_product_main_image_cleanup_batch_processor_version",
        table_name="product_main_image_cleanup_batch",
    )
    op.drop_index(
        "ix_product_main_image_cleanup_batch_processor_method",
        table_name="product_main_image_cleanup_batch",
    )
    op.drop_index(
        "ix_product_main_image_cleanup_batch_status",
        table_name="product_main_image_cleanup_batch",
    )
    op.drop_table("product_main_image_cleanup_batch")
