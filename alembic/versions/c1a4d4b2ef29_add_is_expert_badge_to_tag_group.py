"""add is_expert_badge to tag_group

Revision ID: c1a4d4b2ef29
Revises: b3c1f9a8d2e4
Create Date: 2026-02-14 17:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1a4d4b2ef29"
down_revision: Union[str, Sequence[str], None] = "b3c1f9a8d2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tag_group",
        sa.Column("is_expert_badge", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_tag_group_is_expert_badge",
        "tag_group",
        ["is_expert_badge"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
            UPDATE tag_group
            SET is_expert_badge = TRUE
            WHERE slug = 'expert-badge'
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE tag_group
            SET is_public = FALSE
            WHERE slug IN ('wifi', 'winter', 'noise', 'area', 'inverter')
               OR slug LIKE 'wifi-%'
               OR slug LIKE 'winter-%'
               OR slug LIKE 'noise-%'
               OR slug LIKE 'area-%'
               OR slug LIKE 'inverter-%'
            """
        )
    )

    op.alter_column("tag_group", "is_expert_badge", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_tag_group_is_expert_badge", table_name="tag_group")
    op.drop_column("tag_group", "is_expert_badge")
