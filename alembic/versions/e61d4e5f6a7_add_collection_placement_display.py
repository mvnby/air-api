"""Add placement-owned collection presentation settings.

Revision ID: e61d4e5f6a7
Revises: e60c3d4e5f6
"""
from alembic import op
import sqlalchemy as sa

revision = "e61d4e5f6a7"
down_revision = "e60c3d4e5f6"
branch_labels = None
depends_on = None

CONSTRAINTS = {
    "ck_collection_placement_display_mode": "display_mode IN ('carousel', 'grid', 'tiles', 'single')",
    "ck_collection_placement_item_limit": "item_limit IS NULL OR (item_limit >= 1 AND item_limit <= 24)",
    "ck_collection_placement_grid_columns": "grid_columns >= 2 AND grid_columns <= 4",
    "ck_collection_placement_rotation_mode": "rotation_mode IN ('none', 'daily') AND (rotation_mode = 'none' OR display_mode = 'single')",
}


def upgrade() -> None:
    op.add_column("product_collection_placement", sa.Column("display_mode", sa.String(16), nullable=False, server_default="carousel"))
    op.add_column("product_collection_placement", sa.Column("item_limit", sa.Integer(), nullable=True))
    op.add_column("product_collection_placement", sa.Column("grid_columns", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("product_collection_placement", sa.Column("rotation_mode", sa.String(16), nullable=False, server_default="none"))
    # Existing featured tabs used a four-column desktop grid. Initialize only
    # the new presentation fields so migration does not change that layout.
    op.execute(sa.text(
        "UPDATE product_collection_placement "
        "SET display_mode = 'grid', grid_columns = 4 "
        "WHERE surface_key = 'home' AND slot_key = 'featured_products'"
    ))
    for name, expression in CONSTRAINTS.items():
        op.create_check_constraint(name, "product_collection_placement", expression)


def downgrade() -> None:
    for name in reversed(CONSTRAINTS):
        op.drop_constraint(name, "product_collection_placement", type_="check")
    for column in ("rotation_mode", "grid_columns", "item_limit", "display_mode"):
        op.drop_column("product_collection_placement", column)
