"""Add scoped personal offer drafts and immutable publication snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "t1286offer01"
down_revision = "order1278diag01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "personal_offer",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("order.id", ondelete="SET NULL")),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rooms", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ("storefront_id", "tenant_id"), ("storefront.id", "storefront.tenant_id"),
            name="fk_personal_offer_storefront_scope",
        ),
    )
    op.create_index("ix_personal_offer_scope", "personal_offer", ["tenant_id", "storefront_id", "id"])
    op.create_index(
        "ix_personal_offer_order_scope", "personal_offer",
        ["tenant_id", "storefront_id", "order_id", "id"],
    )
    op.create_table(
        "personal_offer_publication",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("personal_offer.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("draft_version", sa.Integer(), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("encrypted_token", sa.Text(), nullable=False),
        sa.Column("hostname", sa.String(253), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("offer_id", "request_id", name="uq_personal_offer_publication_receipt"),
        sa.UniqueConstraint("token_digest", name="uq_personal_offer_publication_token_digest"),
    )
    op.create_index(
        "uq_personal_offer_current_publication", "personal_offer_publication", ["offer_id"], unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"), sqlite_where=sa.text("revoked_at IS NULL"),
    )


def downgrade():
    op.drop_table("personal_offer_publication")
    op.drop_table("personal_offer")
