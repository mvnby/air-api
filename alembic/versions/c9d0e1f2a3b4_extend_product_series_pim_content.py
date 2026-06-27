"""extend product series pim content

Revision ID: c9d0e1f2a3b4
Revises: b1c2d3e4f5a6
Create Date: 2026-06-27 15:55:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("product_series", sa.Column("tagline", sa.String(), nullable=True))
    op.add_column("product_series", sa.Column("short_description", sa.Text(), nullable=True))
    op.add_column(
        "product_series",
        sa.Column("gallery_images", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "product_series",
        sa.Column("feature_blocks", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "product_series",
        sa.Column("content_blocks", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "product_series",
        sa.Column("footnotes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column("product_series", sa.Column("seo_title", sa.String(), nullable=True))
    op.add_column("product_series", sa.Column("seo_description", sa.Text(), nullable=True))
    op.add_column("product_series", sa.Column("source_url", sa.String(), nullable=True))

    for column_name in ("gallery_images", "feature_blocks", "content_blocks", "footnotes"):
        op.alter_column("product_series", column_name, server_default=None)


def downgrade() -> None:
    op.drop_column("product_series", "source_url")
    op.drop_column("product_series", "seo_description")
    op.drop_column("product_series", "seo_title")
    op.drop_column("product_series", "footnotes")
    op.drop_column("product_series", "content_blocks")
    op.drop_column("product_series", "feature_blocks")
    op.drop_column("product_series", "gallery_images")
    op.drop_column("product_series", "short_description")
    op.drop_column("product_series", "tagline")
