"""Add private facsimile assets and signed PDF artifacts.

Revision ID: fa0b1c2d3e4f
Revises: a9d1e2f3b4c5
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa


revision = "fa0b1c2d3e4f"
down_revision = "a9d1e2f3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_facsimile_asset",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("legal_entity_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("storage_key", sa.String(1000), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(
            ["legal_entity_id", "tenant_id"],
            ["document_legal_entity.id", "document_legal_entity.tenant_id"],
            name="fk_document_facsimile_asset_legal_entity_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("kind IN ('signature', 'seal')", name="ck_document_facsimile_asset_kind"),
        sa.CheckConstraint("size_bytes > 0", name="ck_document_facsimile_asset_size"),
    )
    op.create_index("ix_document_facsimile_asset_tenant_id", "document_facsimile_asset", ["tenant_id"])
    op.create_index("ix_document_facsimile_asset_legal_entity_id", "document_facsimile_asset", ["legal_entity_id"])
    op.create_index("ix_document_facsimile_asset_kind", "document_facsimile_asset", ["kind"])
    op.create_index(
        "uq_document_facsimile_asset_current_kind", "document_facsimile_asset",
        ["tenant_id", "legal_entity_id", "kind"], unique=True,
        postgresql_where=sa.text("is_current"), sqlite_where=sa.text("is_current = 1"),
    )
    op.create_table(
        "document_template_facsimile_placement",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_version_id", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("signature_x_mm", sa.Float(), nullable=False),
        sa.Column("signature_y_mm", sa.Float(), nullable=False),
        sa.Column("signature_width_mm", sa.Float(), nullable=False),
        sa.Column("seal_x_mm", sa.Float(), nullable=False),
        sa.Column("seal_y_mm", sa.Float(), nullable=False),
        sa.Column("seal_width_mm", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["template_version_id"], ["document_template_version.id"]),
        sa.UniqueConstraint("template_version_id", name="uq_document_template_facsimile_placement_version"),
        sa.CheckConstraint("page_number > 0", name="ck_document_template_facsimile_placement_page"),
        sa.CheckConstraint("signature_width_mm > 0 AND seal_width_mm > 0", name="ck_document_template_facsimile_placement_width"),
    )
    op.create_index("ix_document_template_facsimile_placement_template_version_id", "document_template_facsimile_placement", ["template_version_id"])
    with op.batch_alter_table("document_artifact") as batch:
        batch.drop_constraint("ck_document_artifact_kind_valid", type_="check")
        batch.create_check_constraint("ck_document_artifact_kind_valid", "kind IN ('source_docx', 'rendered_docx', 'pdf', 'signed_pdf')")


def downgrade() -> None:
    with op.batch_alter_table("document_artifact") as batch:
        batch.drop_constraint("ck_document_artifact_kind_valid", type_="check")
        batch.create_check_constraint("ck_document_artifact_kind_valid", "kind IN ('source_docx', 'rendered_docx', 'pdf')")
    op.drop_table("document_template_facsimile_placement")
    op.drop_table("document_facsimile_asset")
