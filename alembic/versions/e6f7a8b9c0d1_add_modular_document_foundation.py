"""add modular document foundation

Revision ID: e6f7a8b9c0d1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _set_legacy_google_columns_nullable(*, nullable: bool) -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("document_template") as batch_op:
            batch_op.alter_column(
                "google_template_id",
                existing_type=sa.String(),
                nullable=nullable,
            )
        with op.batch_alter_table("order_document") as batch_op:
            batch_op.alter_column(
                "google_file_id",
                existing_type=sa.String(),
                nullable=nullable,
            )
            batch_op.alter_column(
                "google_edit_url",
                existing_type=sa.String(),
                nullable=nullable,
            )
        return
    op.alter_column(
        "document_template",
        "google_template_id",
        existing_type=sa.String(),
        nullable=nullable,
    )
    op.alter_column(
        "order_document",
        "google_file_id",
        existing_type=sa.String(),
        nullable=nullable,
    )
    op.alter_column(
        "order_document",
        "google_edit_url",
        existing_type=sa.String(),
        nullable=nullable,
    )


def upgrade() -> None:
    _set_legacy_google_columns_nullable(nullable=True)
    op.create_table(
        "document_legal_entity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("legal_name", sa.String(length=500), nullable=True),
        sa.Column("unp", sa.String(length=32), nullable=True),
        sa.Column("is_vat_payer", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("requisites", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(trim(slug)) > 0",
            name="ck_document_legal_entity_slug_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(display_name)) > 0",
            name="ck_document_legal_entity_name_nonempty",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_document_legal_entity_status_valid",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "tenant_id", name="uq_document_legal_entity_id_tenant"
        ),
        sa.UniqueConstraint(
            "tenant_id", "slug", name="uq_document_legal_entity_tenant_slug"
        ),
    )
    op.create_index(
        "ix_document_legal_entity_tenant_id",
        "document_legal_entity",
        ["tenant_id"],
    )
    op.create_index(
        "ix_document_legal_entity_status",
        "document_legal_entity",
        ["status"],
    )
    op.create_index(
        "uq_document_legal_entity_default_per_tenant",
        "document_legal_entity",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
        sqlite_where=sa.text("is_default = 1"),
    )

    op.add_column(
        "document_template", sa.Column("tenant_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "document_template", sa.Column("legal_entity_id", sa.Integer(), nullable=True)
    )
    op.create_index(
        "ix_document_template_tenant_id", "document_template", ["tenant_id"]
    )
    op.create_index(
        "ix_document_template_legal_entity_id",
        "document_template",
        ["legal_entity_id"],
    )
    if _is_postgresql():
        op.create_foreign_key(
            "fk_document_template_tenant_id",
            "document_template",
            "tenant",
            ["tenant_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_document_template_legal_entity_tenant",
            "document_template",
            "document_legal_entity",
            ["legal_entity_id", "tenant_id"],
            ["id", "tenant_id"],
            ondelete="RESTRICT",
        )
        op.create_check_constraint(
            "ck_document_template_legal_entity_requires_tenant",
            "document_template",
            "legal_entity_id IS NULL OR tenant_id IS NOT NULL",
        )

    op.create_table(
        "document_template_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("renderer", sa.String(length=32), nullable=False),
        sa.Column("source_storage_key", sa.String(length=500), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("placeholder_schema", sa.JSON(), nullable=False),
        sa.Column("change_note", sa.String(length=1000), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_document_template_version_positive"),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'retired')",
            name="ck_document_template_version_status_valid",
        ),
        sa.CheckConstraint(
            "renderer IN ('docx', 'google_docs', 'google_sheets')",
            name="ck_document_template_version_renderer_valid",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["document_template.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_id",
            "version",
            name="uq_document_template_version_number",
        ),
    )
    op.create_index(
        "ix_document_template_version_template_id",
        "document_template_version",
        ["template_id"],
    )
    op.create_index(
        "ix_document_template_version_status",
        "document_template_version",
        ["status"],
    )
    op.create_index(
        "uq_document_template_version_active",
        "document_template_version",
        ["template_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

    op.add_column("order_document", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.add_column(
        "order_document", sa.Column("legal_entity_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "order_document", sa.Column("status", sa.String(length=24), nullable=True)
    )
    op.add_column(
        "order_document",
        sa.Column("internal_reference", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "order_document",
        sa.Column("official_series", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "order_document",
        sa.Column("official_period_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "order_document",
        sa.Column("official_number", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "order_document", sa.Column("official_date", sa.Date(), nullable=True)
    )
    op.add_column(
        "order_document",
        sa.Column("business_role", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "order_document", sa.Column("snapshot_version", sa.Integer(), nullable=True)
    )
    op.add_column(
        "order_document", sa.Column("render_snapshot", sa.JSON(), nullable=True)
    )
    op.add_column(
        "order_document", sa.Column("template_version_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "order_document", sa.Column("replaces_document_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "order_document",
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "order_document",
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "order_document",
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "order_document",
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "order_document",
        sa.Column("void_reason", sa.String(length=1000), nullable=True),
    )
    for column_name in (
        "tenant_id",
        "legal_entity_id",
        "status",
        "business_role",
        "template_version_id",
        "replaces_document_id",
    ):
        op.create_index(
            f"ix_order_document_{column_name}",
            "order_document",
            [column_name],
        )
    op.create_index(
        "uq_order_document_internal_reference",
        "order_document",
        ["tenant_id", "internal_reference"],
        unique=True,
        postgresql_where=sa.text(
            "tenant_id IS NOT NULL AND internal_reference IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "tenant_id IS NOT NULL AND internal_reference IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_order_document_official_identity",
        "order_document",
        [
            "tenant_id",
            "legal_entity_id",
            "doc_type",
            "official_series",
            "official_period_key",
            "official_number",
        ],
        unique=True,
        postgresql_where=sa.text(
            "tenant_id IS NOT NULL AND legal_entity_id IS NOT NULL "
            "AND official_number IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "tenant_id IS NOT NULL AND legal_entity_id IS NOT NULL "
            "AND official_number IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_order_document_id_tenant",
        "order_document",
        ["id", "tenant_id"],
        unique=True,
    )
    op.create_index(
        "uq_order_document_id_tenant_legal_entity",
        "order_document",
        ["id", "tenant_id", "legal_entity_id"],
        unique=True,
    )
    op.create_index(
        "uq_order_document_active_replacement",
        "order_document",
        ["tenant_id", "replaces_document_id"],
        unique=True,
        postgresql_where=sa.text(
            "replaces_document_id IS NOT NULL AND status IN ('draft', 'issued', 'sent', 'signed')"
        ),
        sqlite_where=sa.text(
            "replaces_document_id IS NOT NULL AND status IN ('draft', 'issued', 'sent', 'signed')"
        ),
    )
    if _is_postgresql():
        op.create_foreign_key(
            "fk_order_document_tenant_id",
            "order_document",
            "tenant",
            ["tenant_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_order_document_legal_entity_tenant",
            "order_document",
            "document_legal_entity",
            ["legal_entity_id", "tenant_id"],
            ["id", "tenant_id"],
            ondelete="RESTRICT",
        )
        op.create_foreign_key(
            "fk_order_document_template_version_id",
            "order_document",
            "document_template_version",
            ["template_version_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_foreign_key(
            "fk_order_document_replaces_document_id",
            "order_document",
            "order_document",
            ["replaces_document_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_check_constraint(
            "ck_order_document_legal_entity_requires_tenant",
            "order_document",
            "legal_entity_id IS NULL OR tenant_id IS NOT NULL",
        )
        op.create_check_constraint(
            "ck_order_document_status_valid",
            "order_document",
            "status IS NULL OR status IN ('draft', 'issued', 'sent', 'signed', 'void', 'replaced')",
        )
        op.create_check_constraint(
            "ck_order_document_managed_scope_complete",
            "order_document",
            "status IS NULL OR (tenant_id IS NOT NULL AND legal_entity_id IS NOT NULL "
            "AND internal_reference IS NOT NULL)",
        )
        op.create_check_constraint(
            "ck_order_document_official_identity_complete",
            "order_document",
            "official_number IS NULL OR (tenant_id IS NOT NULL AND legal_entity_id IS NOT NULL "
            "AND official_series IS NOT NULL AND official_period_key IS NOT NULL "
            "AND official_date IS NOT NULL)",
        )
        op.create_check_constraint(
            "ck_order_document_business_role_valid",
            "order_document",
            "business_role IS NULL OR business_role IN ('payment_request', 'offer')",
        )

    op.create_table(
        "document_artifact",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("order_document_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("storage_key", sa.String(length=1000), nullable=False),
        sa.Column("content_type", sa.String(length=160), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("is_authoritative", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('source_docx', 'rendered_docx', 'pdf')",
            name="ck_document_artifact_kind_valid",
        ),
        sa.CheckConstraint(
            "length(trim(provider)) > 0",
            name="ck_document_artifact_provider_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(storage_key)) > 0",
            name="ck_document_artifact_storage_key_nonempty",
        ),
        sa.CheckConstraint(
            "size_bytes >= 0",
            name="ck_document_artifact_size_non_negative",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(
            ["order_document_id", "tenant_id"],
            ["order_document.id", "order_document.tenant_id"],
            name="fk_document_artifact_order_document_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_artifact_tenant_id", "document_artifact", ["tenant_id"]
    )
    op.create_index(
        "ix_document_artifact_order_document_id",
        "document_artifact",
        ["order_document_id"],
    )
    op.create_index("ix_document_artifact_kind", "document_artifact", ["kind"])
    op.create_index(
        "uq_document_artifact_authoritative_kind",
        "document_artifact",
        ["order_document_id", "kind"],
        unique=True,
        postgresql_where=sa.text("is_authoritative"),
        sqlite_where=sa.text("is_authoritative = 1"),
    )

    op.create_table(
        "document_number_policy",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("legal_entity_id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("series", sa.String(length=64), nullable=False),
        sa.Column("period_mode", sa.String(length=32), nullable=False),
        sa.Column("minimum_width", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "period_mode IN ('calendar_year', 'continuous', 'per_basis')",
            name="ck_document_number_policy_period_mode_valid",
        ),
        sa.CheckConstraint(
            "minimum_width >= 1 AND minimum_width <= 12",
            name="ck_document_number_policy_width_valid",
        ),
        sa.CheckConstraint(
            "length(trim(document_type)) > 0",
            name="ck_document_number_policy_type_nonempty",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(
            ["legal_entity_id", "tenant_id"],
            ["document_legal_entity.id", "document_legal_entity.tenant_id"],
            name="fk_document_number_policy_legal_entity_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "legal_entity_id",
            "document_type",
            name="uq_document_number_policy_scope",
        ),
    )
    op.create_index(
        "ix_document_number_policy_tenant_id", "document_number_policy", ["tenant_id"]
    )
    op.create_index(
        "ix_document_number_policy_legal_entity_id",
        "document_number_policy",
        ["legal_entity_id"],
    )
    op.create_index(
        "ix_document_number_policy_document_type",
        "document_number_policy",
        ["document_type"],
    )

    op.create_table(
        "document_number_sequence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("legal_entity_id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("series", sa.String(length=64), nullable=False),
        sa.Column("period_key", sa.String(length=32), nullable=False),
        sa.Column("last_value", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "last_value >= 0", name="ck_document_number_sequence_non_negative"
        ),
        sa.CheckConstraint(
            "length(trim(document_type)) > 0",
            name="ck_document_number_sequence_type_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(period_key)) > 0",
            name="ck_document_number_sequence_period_nonempty",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(
            ["legal_entity_id", "tenant_id"],
            ["document_legal_entity.id", "document_legal_entity.tenant_id"],
            name="fk_document_number_sequence_legal_entity_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "legal_entity_id",
            "document_type",
            "series",
            "period_key",
            name="uq_document_number_sequence_scope",
        ),
    )
    op.create_index(
        "ix_document_number_sequence_tenant_id",
        "document_number_sequence",
        ["tenant_id"],
    )
    op.create_index(
        "ix_document_number_sequence_legal_entity_id",
        "document_number_sequence",
        ["legal_entity_id"],
    )

    op.create_table(
        "document_number_reservation",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("legal_entity_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("series", sa.String(length=64), nullable=False),
        sa.Column("period_key", sa.String(length=32), nullable=False),
        sa.Column("number_value", sa.Integer(), nullable=False),
        sa.Column("number_text", sa.String(length=160), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "number_value > 0",
            name="ck_document_number_reservation_positive",
        ),
        sa.CheckConstraint(
            "status IN ('reserved', 'assigned', 'void')",
            name="ck_document_number_reservation_status_valid",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(
            ["legal_entity_id", "tenant_id"],
            ["document_legal_entity.id", "document_legal_entity.tenant_id"],
            name="fk_document_number_reservation_legal_entity_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "tenant_id", "legal_entity_id"],
            [
                "order_document.id",
                "order_document.tenant_id",
                "order_document.legal_entity_id",
            ],
            name="fk_document_number_reservation_document_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "legal_entity_id",
            "document_type",
            "series",
            "period_key",
            "number_value",
            name="uq_document_number_reservation_value",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_document_number_reservation_idempotency",
        ),
    )
    for column_name in ("tenant_id", "legal_entity_id", "document_id", "status"):
        op.create_index(
            f"ix_document_number_reservation_{column_name}",
            "document_number_reservation",
            [column_name],
        )
    op.create_index(
        "uq_document_number_reservation_document",
        "document_number_reservation",
        ["tenant_id", "document_id"],
        unique=True,
        postgresql_where=sa.text("document_id IS NOT NULL"),
        sqlite_where=sa.text("document_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_document_number_reservation_document",
        table_name="document_number_reservation",
    )
    for column_name in ("status", "document_id", "legal_entity_id", "tenant_id"):
        op.drop_index(
            f"ix_document_number_reservation_{column_name}",
            table_name="document_number_reservation",
        )
    op.drop_table("document_number_reservation")

    op.drop_index(
        "ix_document_number_sequence_legal_entity_id",
        table_name="document_number_sequence",
    )
    op.drop_index(
        "ix_document_number_sequence_tenant_id",
        table_name="document_number_sequence",
    )
    op.drop_table("document_number_sequence")

    op.drop_index(
        "ix_document_number_policy_document_type",
        table_name="document_number_policy",
    )
    op.drop_index(
        "ix_document_number_policy_legal_entity_id",
        table_name="document_number_policy",
    )
    op.drop_index(
        "ix_document_number_policy_tenant_id",
        table_name="document_number_policy",
    )
    op.drop_table("document_number_policy")

    op.drop_index(
        "uq_document_artifact_authoritative_kind",
        table_name="document_artifact",
    )
    op.drop_index("ix_document_artifact_kind", table_name="document_artifact")
    op.drop_index(
        "ix_document_artifact_order_document_id",
        table_name="document_artifact",
    )
    op.drop_index("ix_document_artifact_tenant_id", table_name="document_artifact")
    op.drop_table("document_artifact")

    if _is_postgresql():
        for constraint_name, constraint_type in (
            ("ck_order_document_business_role_valid", "check"),
            ("ck_order_document_official_identity_complete", "check"),
            ("ck_order_document_managed_scope_complete", "check"),
            ("ck_order_document_status_valid", "check"),
            ("ck_order_document_legal_entity_requires_tenant", "check"),
            ("fk_order_document_replaces_document_id", "foreignkey"),
            ("fk_order_document_template_version_id", "foreignkey"),
            ("fk_order_document_legal_entity_tenant", "foreignkey"),
            ("fk_order_document_tenant_id", "foreignkey"),
        ):
            op.drop_constraint(
                constraint_name,
                "order_document",
                type_=constraint_type,
            )
    op.drop_index("uq_order_document_active_replacement", table_name="order_document")
    op.drop_index(
        "uq_order_document_id_tenant_legal_entity", table_name="order_document"
    )
    op.drop_index("uq_order_document_id_tenant", table_name="order_document")
    op.drop_index("uq_order_document_official_identity", table_name="order_document")
    op.drop_index("uq_order_document_internal_reference", table_name="order_document")
    for column_name in (
        "replaces_document_id",
        "template_version_id",
        "business_role",
        "status",
        "legal_entity_id",
        "tenant_id",
    ):
        op.drop_index(f"ix_order_document_{column_name}", table_name="order_document")
    for column_name in (
        "void_reason",
        "voided_at",
        "signed_at",
        "sent_at",
        "issued_at",
        "replaces_document_id",
        "template_version_id",
        "official_date",
        "official_number",
        "official_period_key",
        "official_series",
        "render_snapshot",
        "snapshot_version",
        "business_role",
        "internal_reference",
        "status",
        "legal_entity_id",
        "tenant_id",
    ):
        op.drop_column("order_document", column_name)

    op.drop_index(
        "uq_document_template_version_active",
        table_name="document_template_version",
    )
    op.drop_index(
        "ix_document_template_version_status",
        table_name="document_template_version",
    )
    op.drop_index(
        "ix_document_template_version_template_id",
        table_name="document_template_version",
    )
    op.drop_table("document_template_version")

    if _is_postgresql():
        op.drop_constraint(
            "ck_document_template_legal_entity_requires_tenant",
            "document_template",
            type_="check",
        )
        op.drop_constraint(
            "fk_document_template_legal_entity_tenant",
            "document_template",
            type_="foreignkey",
        )
        op.drop_constraint(
            "fk_document_template_tenant_id",
            "document_template",
            type_="foreignkey",
        )
    op.drop_index(
        "ix_document_template_legal_entity_id", table_name="document_template"
    )
    op.drop_index("ix_document_template_tenant_id", table_name="document_template")
    op.drop_column("document_template", "legal_entity_id")
    op.drop_column("document_template", "tenant_id")

    op.drop_index("ix_document_legal_entity_status", table_name="document_legal_entity")
    op.drop_index(
        "uq_document_legal_entity_default_per_tenant",
        table_name="document_legal_entity",
    )
    op.drop_index(
        "ix_document_legal_entity_tenant_id", table_name="document_legal_entity"
    )
    op.drop_table("document_legal_entity")
    # Keep the three legacy Google columns nullable on downgrade. Restoring
    # NOT NULL would either fail for native rows or require destructive data
    # fabrication/deletion, which is outside this expand migration's contract.
