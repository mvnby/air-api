"""add product attachments and import media cache

Revision ID: 1f2e3d4c5b6a
Revises: b7d8e9f0a1b2
Create Date: 2026-04-20 15:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "1f2e3d4c5b6a"
down_revision: Union[str, Sequence[str], None] = "b7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_attachment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("title", sa.String(), nullable=False, server_default=sa.text("'Инструкция'")),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id",
            "kind",
            "url",
            name="uq_product_attachment_product_kind_url",
        ),
    )
    op.create_index(
        "ix_product_attachment_product_id",
        "product_attachment",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        "ix_product_attachment_kind",
        "product_attachment",
        ["kind"],
        unique=False,
    )
    op.create_index(
        "ix_product_attachment_source",
        "product_attachment",
        ["source"],
        unique=False,
    )

    op.create_table(
        "import_media_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("local_url", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_url", name="uq_import_media_cache_source_url"),
    )
    op.create_index(
        "ix_import_media_cache_source_url",
        "import_media_cache",
        ["source_url"],
        unique=False,
    )
    op.create_index(
        "ix_import_media_cache_content_hash",
        "import_media_cache",
        ["content_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_import_media_cache_content_hash", table_name="import_media_cache")
    op.drop_index("ix_import_media_cache_source_url", table_name="import_media_cache")
    op.drop_table("import_media_cache")

    op.drop_index("ix_product_attachment_source", table_name="product_attachment")
    op.drop_index("ix_product_attachment_kind", table_name="product_attachment")
    op.drop_index("ix_product_attachment_product_id", table_name="product_attachment")
    op.drop_table("product_attachment")
