"""add typed installation drafts and immutable published price books

Revision ID: e69c2d4e6f80
Revises: e68b7c9d0e1f
"""

import sqlalchemy as sa
from alembic import op

revision = "e69c2d4e6f80"
down_revision = "e68b7c9d0e1f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("service_tariff", sa.Column("installation_match", sa.JSON(), nullable=True))
    op.add_column("service_tariff", sa.Column("installation_code", sa.String(), nullable=True))
    op.create_index("ix_service_tariff_installation_code", "service_tariff", ["installation_code"])
    op.add_column("service_tariff", sa.Column("installation_price_mode", sa.String(), nullable=False, server_default="fixed"))
    op.add_column("service_tariff", sa.Column("included_holes_by_type", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("service_tariff_rule", sa.Column("component_code", sa.String(), nullable=True))
    op.create_index("ix_service_tariff_rule_component_code", "service_tariff_rule", ["component_code"])
    op.create_table(
        "installation_price_book",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("entries", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_by", sa.String(), nullable=True),
        sa.UniqueConstraint("tenant_id", "revision", name="uq_installation_book_tenant_revision"),
    )
    op.create_index("ix_installation_price_book_tenant_id", "installation_price_book", ["tenant_id"])
    op.create_index("ix_installation_price_book_revision", "installation_price_book", ["revision"])
    op.create_index("ix_installation_price_book_fingerprint", "installation_price_book", ["fingerprint"])
    op.create_table(
        "installation_preview_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("storefront_id", sa.Integer(), sa.ForeignKey("storefront.id"), nullable=False),
        sa.Column("price_book_id", sa.Integer(), sa.ForeignKey("installation_price_book.id"), nullable=False),
        sa.Column("input_hash", sa.String(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name in ("token_hash", "tenant_id", "storefront_id", "price_book_id", "expires_at"):
        op.create_index(f"ix_installation_preview_snapshot_{name}", "installation_preview_snapshot", [name], unique=name == "token_hash")


def downgrade() -> None:
    op.drop_table("installation_preview_snapshot")
    op.drop_table("installation_price_book")
    op.drop_index("ix_service_tariff_rule_component_code", table_name="service_tariff_rule")
    op.drop_column("service_tariff_rule", "component_code")
    op.drop_column("service_tariff", "included_holes_by_type")
    op.drop_column("service_tariff", "installation_price_mode")
    op.drop_column("service_tariff", "installation_match")
    op.drop_index("ix_service_tariff_installation_code", table_name="service_tariff")
    op.drop_column("service_tariff", "installation_code")
