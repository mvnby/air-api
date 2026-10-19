"""Add contextual feature presentation and official brand research sources.

Additive migration: existing content and presentation remain unchanged.
"""

from alembic import op
import sqlalchemy as sa

revision = "cat20261019feat03"
down_revision = "cat20261019doc02"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("brand", sa.Column("official_url", sa.String(2048), nullable=True))
    op.add_column("feature", sa.Column("icon_caption", sa.String(160), nullable=True))
    for target in ("brand", "series", "product"):
        table = f"feature_{target}_link"
        op.add_column(table, sa.Column("display_mode", sa.String(16), nullable=True))
        op.create_check_constraint(
            f"ck_feature_{target}_display_mode",
            table,
            "display_mode IS NULL OR display_mode IN ('icon', 'compact', 'detailed')",
        )


def downgrade():
    for target in ("product", "series", "brand"):
        table = f"feature_{target}_link"
        op.drop_constraint(f"ck_feature_{target}_display_mode", table, type_="check")
        op.drop_column(table, "display_mode")
    op.drop_column("feature", "icon_caption")
    op.drop_column("brand", "official_url")
