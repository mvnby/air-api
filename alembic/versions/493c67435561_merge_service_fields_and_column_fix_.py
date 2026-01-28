"""merge service fields and column fix branches

Revision ID: 493c67435561
Revises: 54bd106a3275, c6fb1dd4d4e0
Create Date: 2026-01-28 13:05:51.771200

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '493c67435561'
down_revision: Union[str, Sequence[str], None] = ('54bd106a3275', 'c6fb1dd4d4e0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
