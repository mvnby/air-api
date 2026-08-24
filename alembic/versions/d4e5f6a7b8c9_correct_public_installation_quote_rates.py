"""correct public installation manual-quote rates

Revision ID: d4e5f6a7b8c9
Revises: e3c4d5e6f7a8
Create Date: 2026-08-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "e3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _update_rate(*, category: str, old_price: int, new_price: int) -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE installation_rates
            SET base_price = :new_price
            WHERE category = :category
              AND power_range = 'All'
              AND base_price = :old_price
            """
        ),
        {"category": category, "old_price": old_price, "new_price": new_price},
    )


def upgrade() -> None:
    _update_rate(category="Cassette", old_price=1200, new_price=1500)
    _update_rate(category="Ceiling", old_price=1200, new_price=1400)


def downgrade() -> None:
    _update_rate(category="Cassette", old_price=1500, new_price=1200)
    _update_rate(category="Ceiling", old_price=1400, new_price=1200)
