"""Persist addressed template reviews and inactive proposal provenance."""

from alembic import op
import sqlalchemy as sa

revision = "doc20261110audit01"
down_revision = "mcp20261105unit01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_template_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False
        ),
        sa.Column(
            "legal_entity_id",
            sa.Integer(),
            sa.ForeignKey("document_legal_entity.id"),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("document_template.id"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            sa.Integer(),
            sa.ForeignKey("document_template_version.id"),
            nullable=False,
        ),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customer.id")),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column("legal_sources_hash", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_date", sa.String(), nullable=False),
        sa.Column("coverage", sa.JSON(), nullable=False),
        sa.Column("checklist", sa.JSON(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column(
            "created_by", sa.Integer(), sa.ForeignKey("staff_users.id"), nullable=False
        ),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "template_id",
            "version_id",
            "context_hash",
            name="uq_template_audit_context",
        ),
    )
    for column in ("tenant_id", "legal_entity_id", "template_id", "version_id"):
        op.create_index(
            f"ix_document_template_audit_{column}", "document_template_audit", [column]
        )
    op.create_table(
        "document_template_audit_proposal",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False
        ),
        sa.Column(
            "report_id",
            sa.Integer(),
            sa.ForeignKey("document_template_audit.id"),
            nullable=False,
        ),
        sa.Column(
            "base_version_id",
            sa.Integer(),
            sa.ForeignKey("document_template_version.id"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            sa.Integer(),
            sa.ForeignKey("document_template_version.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column("legal_sources_hash", sa.String(64), nullable=False),
        sa.Column("edits", sa.JSON(), nullable=False),
        sa.Column(
            "created_by", sa.Integer(), sa.ForeignKey("staff_users.id"), nullable=False
        ),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("tenant_id", "report_id"):
        op.create_index(
            f"ix_document_template_audit_proposal_{column}",
            "document_template_audit_proposal",
            [column],
        )


def downgrade():
    op.drop_table("document_template_audit_proposal")
    op.drop_table("document_template_audit")
