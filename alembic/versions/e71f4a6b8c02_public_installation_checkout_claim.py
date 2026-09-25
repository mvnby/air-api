"""Add a durable public checkout claim for accepted installation previews.

Revision ID: e71f4a6b8c02
Revises: e70d3e5f7a91
"""

import sqlalchemy as sa
from alembic import op

revision = "e71f4a6b8c02"
down_revision = "e70d3e5f7a91"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "public_installation_preview_claim",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("preview_token_hash", sa.String(), nullable=False),
        sa.Column("checkout_key_hash", sa.String(), nullable=False),
        sa.Column("request_hash", sa.String(), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("order.id"), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["storefront_id", "tenant_id"], ["storefront.id", "storefront.tenant_id"],
            name="fk_public_installation_claim_storefront_tenant",
        ),
        sa.UniqueConstraint("tenant_id", "storefront_id", "preview_token_hash",
                            name="uq_public_installation_claim_scope_preview"),
        sa.UniqueConstraint("tenant_id", "storefront_id", "checkout_key_hash",
                            name="uq_public_installation_claim_scope_key"),
    )
    op.create_index("ix_public_installation_preview_claim_tenant_id",
                    "public_installation_preview_claim", ["tenant_id"])
    op.create_index("ix_public_installation_preview_claim_storefront_id",
                    "public_installation_preview_claim", ["storefront_id"])


def downgrade() -> None:
    op.drop_table("public_installation_preview_claim")
