"""add unique constraint on product_image (product_id, url)

Revision ID: 9f7c1d2a4b10
Revises: 493c67435561
Create Date: 2026-02-09 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f7c1d2a4b10'
down_revision: Union[str, Sequence[str], None] = '493c67435561'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    # Remove existing duplicates before adding unique constraint.
    conn.execute(sa.text("""
        DELETE FROM product_image
        WHERE id IN (
            SELECT p1.id
            FROM product_image p1
            JOIN product_image p2
              ON p1.product_id = p2.product_id
             AND p1.url = p2.url
             AND p1.id > p2.id
        )
    """))

    with op.batch_alter_table('product_image', schema=None) as batch_op:
        batch_op.create_unique_constraint(
            'uq_product_image_product_id_url',
            ['product_id', 'url'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('product_image', schema=None) as batch_op:
        batch_op.drop_constraint('uq_product_image_product_id_url', type_='unique')
