"""Keep original order evidence files privately with immutable versions."""

from alembic import op
import sqlalchemy as sa

revision = "doc20261120external01"
down_revision = "order1278diag01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("order_document", sa.Column("origin", sa.String(24)))
    op.add_column("order_document", sa.Column("external_status", sa.String(16)))
    op.create_check_constraint(
        "ck_order_document_external_origin", "order_document",
        "(origin IS NULL AND external_status IS NULL) OR "
        "(origin IS NOT NULL AND origin = 'external_upload' AND external_status IN ('received', 'signed') "
        "AND external_status IS NOT NULL AND status IS NULL AND tenant_id IS NOT NULL)",
    )
    op.create_table(
        "order_document_external_file",
        sa.Column("document_id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("storage_key", sa.String(1000), nullable=False),
        sa.Column("uploaded_by_staff_user_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.String(255), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id", "tenant_id"], ["order_document.id", "order_document.tenant_id"],
            name="fk_external_file_document_tenant", ondelete="RESTRICT",
        ),
        sa.CheckConstraint("role IN ('original', 'signed_copy')", name="ck_external_file_role"),
        sa.CheckConstraint("version > 0", name="ck_external_file_version"),
        sa.CheckConstraint("size_bytes > 0", name="ck_external_file_size"),
        sa.CheckConstraint("length(checksum_sha256) = 64", name="ck_external_file_sha256"),
    )


def downgrade():
    recorded = op.get_bind().scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM order_document_external_file) "
        "OR EXISTS (SELECT 1 FROM order_document WHERE origin = 'external_upload')"
    ))
    if recorded:
        raise RuntimeError("External order evidence must be preserved before downgrade")
    op.drop_table("order_document_external_file")
    op.drop_constraint("ck_order_document_external_origin", "order_document", type_="check")
    op.drop_column("order_document", "external_status")
    op.drop_column("order_document", "origin")
