"""add supplier offer match tokens

Revision ID: d2e3f4a5b6c7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-28 03:05:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("supplier_offer", sa.Column("title_normalized", sa.String(), nullable=True))
    op.add_column(
        "supplier_offer",
        sa.Column("model_tokens", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "supplier_offer",
        sa.Column("indoor_model_tokens", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "supplier_offer",
        sa.Column("outdoor_model_tokens", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column("supplier_offer", sa.Column("match_normalizer_version", sa.String(), nullable=True))
    op.create_index(op.f("ix_supplier_offer_title_normalized"), "supplier_offer", ["title_normalized"], unique=False)
    op.create_index(op.f("ix_supplier_offer_match_normalizer_version"), "supplier_offer", ["match_normalizer_version"], unique=False)

    for column_name in ("model_tokens", "indoor_model_tokens", "outdoor_model_tokens"):
        op.alter_column("supplier_offer", column_name, server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_supplier_offer_match_normalizer_version"), table_name="supplier_offer")
    op.drop_index(op.f("ix_supplier_offer_title_normalized"), table_name="supplier_offer")
    op.drop_column("supplier_offer", "match_normalizer_version")
    op.drop_column("supplier_offer", "outdoor_model_tokens")
    op.drop_column("supplier_offer", "indoor_model_tokens")
    op.drop_column("supplier_offer", "model_tokens")
    op.drop_column("supplier_offer", "title_normalized")
