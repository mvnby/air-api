"""fix_product_slug_nullable

Revision ID: 8d38cc21f491
Revises: 50a041157d8e
Create Date: 2026-01-21 18:50:35.292605

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d38cc21f491'
down_revision: Union[str, Sequence[str], None] = '50a041157d8e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # First, generate slugs for any products that don't have them
    connection = op.get_bind()
    
    # Import slugify for slug generation
    from slugify import slugify
    
    # Get products without slugs
    result = connection.execute(sa.text("SELECT id, title FROM product WHERE slug IS NULL"))
    products_without_slugs = result.fetchall()
    
    # Generate and update slugs
    for product_id, title in products_without_slugs:
        slug = slugify(title)
        # Ensure uniqueness by appending ID if needed
        check_result = connection.execute(
            sa.text("SELECT COUNT(*) FROM product WHERE slug = :slug"),
            {"slug": slug}
        )
        if check_result.scalar() > 0:
            slug = f"{slug}-{product_id}"
        
        connection.execute(
            sa.text("UPDATE product SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": product_id}
        )
    
    # Now make slug non-nullable
    with op.batch_alter_table('product', schema=None) as batch_op:
        batch_op.alter_column('slug',
               existing_type=sa.VARCHAR(),
               nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Revert slug to nullable
    with op.batch_alter_table('product', schema=None) as batch_op:
        batch_op.alter_column('slug',
               existing_type=sa.VARCHAR(),
               nullable=True)
