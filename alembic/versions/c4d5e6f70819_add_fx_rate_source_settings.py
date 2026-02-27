"""add_fx_rate_source_settings

Revision ID: c4d5e6f70819
Revises: ab12cd34ef56
Create Date: 2026-02-27 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c4d5e6f70819"
down_revision: Union[str, Sequence[str], None] = "ab12cd34ef56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO global_config (key, value, description, updated_at)
        VALUES
        ('fx_rate_source', 'manual', 'Источник курса USD/BYN: manual | nbrb', NOW()),
        ('supplier_default_spreadsheet_id', '', 'Spreadsheet ID по умолчанию для новых источников', NOW())
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM global_config
        WHERE key IN ('fx_rate_source', 'supplier_default_spreadsheet_id')
        """
    )
