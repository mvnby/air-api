"""Independent manual tender stages and price-enquiry associations."""
from alembic import op
import sqlalchemy as sa

revision = "t1089chain01"
down_revision = "c1086so11d03"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("tender_workflow_context",
        sa.Column("order_id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(24), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("deadline_manual", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["order_id", "tenant_id", "storefront_id"],
            ["order.id", "order.tenant_id", "order.storefront_id"], ondelete="CASCADE"),
        sa.CheckConstraint("stage IN ('price_request','price_sent','announced','submitted','completed')",
            name="ck_tender_workflow_stage"))
    op.create_table("tender_workflow_link",
        sa.Column("publication_order_id", sa.Integer(), primary_key=True),
        sa.Column("price_order_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["publication_order_id", "tenant_id", "storefront_id"],
            ["order.id", "order.tenant_id", "order.storefront_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["price_order_id", "tenant_id", "storefront_id"],
            ["order.id", "order.tenant_id", "order.storefront_id"], ondelete="CASCADE"),
        sa.CheckConstraint("publication_order_id <> price_order_id", name="ck_tender_workflow_distinct"))
    op.create_index("ix_tender_workflow_price_scope", "tender_workflow_link", ["price_order_id", "tenant_id", "storefront_id"])


def downgrade():
    op.drop_table("tender_workflow_link")
    op.drop_table("tender_workflow_context")
