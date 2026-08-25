"""add installation discount policy and product rules

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _legacy_default_discount() -> int:
    value = (
        op.get_bind()
        .execute(
            sa.text("SELECT value FROM global_config WHERE key = 'install_discount'")
        )
        .scalar_one_or_none()
    )
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return 100
    return parsed if 0 <= parsed <= 10_000 else 100


def upgrade() -> None:
    op.create_table(
        "installation_discount_policy",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("default_discount", sa.Integer(), nullable=False),
        sa.Column("minimum_margin", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "id = 1",
            name="ck_installation_discount_policy_singleton",
        ),
        sa.CheckConstraint(
            "default_discount BETWEEN 0 AND 10000",
            name="ck_installation_discount_policy_default_discount",
        ),
        sa.CheckConstraint(
            "minimum_margin BETWEEN 0 AND 1000000",
            name="ck_installation_discount_policy_minimum_margin",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "installation_discount_product_rule",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("discount_amount", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "discount_amount BETWEEN 0 AND 10000",
            name="ck_installation_discount_product_rule_amount",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["product.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("product_id"),
    )
    op.execute(
        sa.insert(
            sa.table(
                "installation_discount_policy",
                sa.column("id", sa.Integer()),
                sa.column("is_enabled", sa.Boolean()),
                sa.column("default_discount", sa.Integer()),
                sa.column("minimum_margin", sa.Integer()),
            )
        ).values(
            id=1,
            is_enabled=False,
            default_discount=_legacy_default_discount(),
            minimum_margin=350,
        )
    )


def downgrade() -> None:
    op.drop_table("installation_discount_product_rule")
    op.drop_table("installation_discount_policy")
