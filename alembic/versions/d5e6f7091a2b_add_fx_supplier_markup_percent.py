"""add_fx_supplier_markup_percent

Revision ID: d5e6f7091a2b
Revises: c4d5e6f70819
Create Date: 2026-02-27 16:22:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d5e6f7091a2b"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f70819"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO global_config (key, value, description, updated_at)
        VALUES
        ('fx_supplier_markup_percent', '2.0', 'Надбавка к курсу USD/BYN для закупки, %', NOW())
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM global_config
        WHERE key IN ('fx_supplier_markup_percent')
        """
    )
