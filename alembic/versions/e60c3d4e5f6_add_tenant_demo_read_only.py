"""Add explicit persisted demo read-only tenant policy.

Revision ID: e60c3d4e5f6
Revises: e59b2c3d4e5f
"""

from alembic import op
import sqlalchemy as sa


revision = "e60c3d4e5f6"
down_revision = "e59b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant",
        sa.Column(
            "demo_read_only",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_table(
        "tenant_demo_fixture_state",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("fixture_version", sa.String(length=24), nullable=False),
        sa.Column("customer_ids", sa.JSON(), nullable=False),
        sa.Column("order_ids", sa.JSON(), nullable=False),
        sa.Column("proposal_ids", sa.JSON(), nullable=False),
        sa.Column("product_line_ids", sa.JSON(), nullable=False),
        sa.Column("offer_ids", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
        ),
        sa.CheckConstraint(
            "fixture_version = 'v1'",
            name="ck_tenant_demo_fixture_version",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_tenant_demo_fixture_storefront_tenant",
        ),
        sa.PrimaryKeyConstraint("tenant_id"),
        sa.UniqueConstraint("storefront_id"),
    )


def downgrade() -> None:
    op.drop_table("tenant_demo_fixture_state")
    op.drop_column("tenant", "demo_read_only")
