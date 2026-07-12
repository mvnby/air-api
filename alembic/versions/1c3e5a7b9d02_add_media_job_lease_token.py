"""add cryptographic lease token to media processing jobs

Revision ID: 1c3e5a7b9d02
Revises: 0b7c8d9e0f12
Create Date: 2026-07-12 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "1c3e5a7b9d02"
down_revision: Union[str, Sequence[str], None] = "0b7c8d9e0f12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "media_processing_jobs",
        sa.Column("lease_token", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("media_processing_jobs", "lease_token")
