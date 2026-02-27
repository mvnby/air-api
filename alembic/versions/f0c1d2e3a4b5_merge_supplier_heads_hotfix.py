"""merge supplier heads hotfix

Revision ID: f0c1d2e3a4b5
Revises: 42a24b21e39f, d5e6f7091a2b
Create Date: 2026-02-27 23:55:00.000000

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "f0c1d2e3a4b5"
down_revision: Union[str, Sequence[str], None] = ("42a24b21e39f", "d5e6f7091a2b")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
