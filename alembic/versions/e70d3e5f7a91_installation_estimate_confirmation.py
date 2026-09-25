"""Add durable installation estimate revisions and proposal line provenance.

Revision ID: e70d3e5f7a91
Revises: e69c2d4e6f80
"""

import sqlalchemy as sa
from alembic import op

revision = "e70d3e5f7a91"
down_revision = "e69c2d4e6f80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "installation_estimate",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("order.id"), nullable=False),
        sa.Column("proposal_id", sa.Integer(), sa.ForeignKey("order_proposal.id"), nullable=False),
        sa.Column("confirmation_key_hash", sa.String(), nullable=False),
        sa.Column("confirmation_request_hash", sa.String(), nullable=False),
        sa.Column("preview_token_hash", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["storefront_id", "tenant_id"], ["storefront.id", "storefront.tenant_id"],
            name="fk_installation_estimate_storefront_tenant",
        ),
        sa.UniqueConstraint("tenant_id", "storefront_id", "confirmation_key_hash",
                            name="uq_installation_estimate_scope_key"),
        sa.UniqueConstraint("tenant_id", "storefront_id", "preview_token_hash", "order_id", "proposal_id",
                            name="uq_installation_estimate_preview_target"),
    )
    for name in ("tenant_id", "storefront_id", "order_id", "proposal_id", "confirmation_key_hash", "preview_token_hash"):
        op.create_index(f"ix_installation_estimate_{name}", "installation_estimate", [name])
    op.create_table(
        "installation_estimate_revision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("estimate_id", sa.Integer(), sa.ForeignKey("installation_estimate.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("price_book_id", sa.Integer(), sa.ForeignKey("installation_price_book.id"), nullable=False),
        sa.Column("price_book_revision", sa.Integer(), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("estimate_id", "revision", name="uq_installation_estimate_revision"),
    )
    op.create_index("ix_installation_estimate_revision_estimate_id", "installation_estimate_revision", ["estimate_id"])
    op.create_index("ix_installation_estimate_revision_price_book_id", "installation_estimate_revision", ["price_book_id"])
    op.add_column("order_service_link", sa.Column("installation_estimate_revision_id", sa.Integer(), nullable=True))
    op.add_column("order_service_link", sa.Column("installation_line_index", sa.Integer(), nullable=True))
    op.add_column("order_service_link", sa.Column("installation_projection_mode", sa.String(), nullable=True))
    op.create_foreign_key("fk_order_service_installation_estimate_revision", "order_service_link",
                          "installation_estimate_revision", ["installation_estimate_revision_id"], ["id"])
    op.create_index("ix_order_service_link_installation_estimate_revision_id", "order_service_link",
                    ["installation_estimate_revision_id"])
    op.create_unique_constraint("uq_order_service_installation_revision_line", "order_service_link",
                                ["proposal_id", "installation_estimate_revision_id", "installation_line_index"])


def downgrade() -> None:
    op.drop_constraint("uq_order_service_installation_revision_line", "order_service_link", type_="unique")
    op.drop_index("ix_order_service_link_installation_estimate_revision_id", table_name="order_service_link")
    op.drop_constraint("fk_order_service_installation_estimate_revision", "order_service_link", type_="foreignkey")
    op.drop_column("order_service_link", "installation_projection_mode")
    op.drop_column("order_service_link", "installation_line_index")
    op.drop_column("order_service_link", "installation_estimate_revision_id")
    op.drop_table("installation_estimate_revision")
    op.drop_table("installation_estimate")
