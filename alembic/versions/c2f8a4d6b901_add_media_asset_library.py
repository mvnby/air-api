"""add media asset library

Revision ID: c2f8a4d6b901
Revises: f6a7b8c9d0e2
Create Date: 2026-06-14 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c2f8a4d6b901"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media_asset",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parent_asset_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("alt_text", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("variant_type", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("original_url", sa.String(), nullable=True),
        sa.Column("source_filename", sa.String(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("storage_provider", sa.String(), nullable=False),
        sa.Column("processing_status", sa.String(), nullable=False),
        sa.Column("processing_error", sa.String(), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["parent_asset_id"], ["media_asset.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "parent_asset_id",
        "title",
        "kind",
        "variant_type",
        "url",
        "source_filename",
        "mime_type",
        "storage_provider",
        "processing_status",
        "content_hash",
        "created_by",
        "created_at",
    ):
        op.create_index(f"ix_media_asset_{column}", "media_asset", [column], unique=False)


def downgrade() -> None:
    for column in (
        "created_at",
        "created_by",
        "content_hash",
        "processing_status",
        "storage_provider",
        "mime_type",
        "source_filename",
        "url",
        "variant_type",
        "kind",
        "title",
        "parent_asset_id",
    ):
        op.drop_index(f"ix_media_asset_{column}", table_name="media_asset")
    op.drop_table("media_asset")
