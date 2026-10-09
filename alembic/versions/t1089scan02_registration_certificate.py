"""Immutable private registration certificates per legal entity."""

from alembic import op
import sqlalchemy as sa

revision = "t1089scan02"
down_revision = "t1089chain01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "legal_entity_attachment",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("legal_entity_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("mime_type", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("storage_key", sa.String(1000), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(
            ["legal_entity_id", "tenant_id"],
            ["document_legal_entity.id", "document_legal_entity.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760"),
        sa.CheckConstraint(
            "mime_type IN ('application/pdf', 'image/jpeg', 'image/png')"
        ),
    )
    op.create_index(
        "ix_legal_entity_attachment_tenant_id", "legal_entity_attachment", ["tenant_id"]
    )
    op.create_index(
        "ix_legal_entity_attachment_legal_entity_id",
        "legal_entity_attachment",
        ["legal_entity_id"],
    )
    op.create_index(
        "uq_legal_entity_attachment_current",
        "legal_entity_attachment",
        ["tenant_id", "legal_entity_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )


def downgrade():
    op.drop_table("legal_entity_attachment")
