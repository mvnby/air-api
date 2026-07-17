"""add bot runtime lease

Revision ID: 8a3c5e7f9b21
Revises: 7f2b4d6e8a10
Create Date: 2026-07-17 17:10:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "8a3c5e7f9b21"
down_revision: Union[str, Sequence[str], None] = "7f2b4d6e8a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "bot_runtime_lease" in inspector.get_table_names():
        return
    op.create_table(
        "bot_runtime_lease",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(length=160), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
    op.create_index("ix_bot_runtime_lease_owner_id", "bot_runtime_lease", ["owner_id"])
    op.create_index("ix_bot_runtime_lease_expires_at", "bot_runtime_lease", ["expires_at"])
    op.create_index("ix_bot_runtime_lease_updated_at", "bot_runtime_lease", ["updated_at"])


def downgrade() -> None:
    if "bot_runtime_lease" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("bot_runtime_lease")
