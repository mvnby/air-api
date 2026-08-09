"""simplify feature contract

Revision ID: f3a4b5c6d7e8
Revises: f2a3b4c5d6e7
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f3a4b5c6d7e8"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("feature", sa.Column("replaces_feature_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_feature_replaces_feature_id",
        "feature",
        "feature",
        ["replaces_feature_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_feature_replaces_feature_id",
        "feature",
        ["replaces_feature_id"],
        unique=False,
    )
    op.add_column(
        "feature_series_link",
        sa.Column("is_featured", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_index(
        "ix_feature_series_link_is_featured",
        "feature_series_link",
        ["is_featured"],
        unique=False,
    )
    op.create_index(
        "ix_feature_series_link_series_featured_sort",
        "feature_series_link",
        ["series_id", "is_featured", "sort_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_feature_series_link_series_featured_sort",
        table_name="feature_series_link",
    )
    op.drop_index("ix_feature_series_link_is_featured", table_name="feature_series_link")
    op.drop_column("feature_series_link", "is_featured")
    op.drop_index("ix_feature_replaces_feature_id", table_name="feature")
    op.drop_constraint("fk_feature_replaces_feature_id", "feature", type_="foreignkey")
    op.drop_column("feature", "replaces_feature_id")
