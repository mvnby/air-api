"""Add provider-neutral document external edit sessions.

Revision ID: b31d9e7a4c62
Revises: f9a0b1c2d3e4
Create Date: 2026-09-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b31d9e7a4c62"
down_revision: Union[str, None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_external_edit_session",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(32), nullable=False),
        sa.Column("template_version_id", sa.Integer(), nullable=True),
        sa.Column("document_artifact_id", sa.String(32), nullable=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_connection_id", sa.String(160), nullable=False),
        sa.Column("remote_file_id", sa.String(500), nullable=True),
        sa.Column("edit_url", sa.String(2000), nullable=True),
        sa.Column("remote_filename", sa.String(255), nullable=True),
        sa.Column("remote_mime_type", sa.String(160), nullable=True),
        sa.Column("base_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("remote_revision", sa.String(500), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("detail", sa.String(1000), nullable=True),
        sa.Column("active_sync_key", sa.String(160), nullable=True),
        sa.Column("active_sync_fingerprint", sa.String(64), nullable=True),
        sa.Column("last_sync_key", sa.String(160), nullable=True),
        sa.Column("last_sync_fingerprint", sa.String(64), nullable=True),
        sa.Column("last_sync_remote_revision", sa.String(500), nullable=True),
        sa.Column("last_imported_template_version_id", sa.Integer(), nullable=True),
        sa.Column("created_by_staff_user_id", sa.Integer(), nullable=True),
        sa.Column("last_synced_by_staff_user_id", sa.Integer(), nullable=True),
        sa.Column("remote_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "subject_type IN ('template_version', 'document_artifact')",
            name="ck_document_external_edit_subject_type_valid",
        ),
        sa.CheckConstraint(
            "(subject_type = 'template_version' "
            "AND template_version_id IS NOT NULL "
            "AND document_artifact_id IS NULL) OR "
            "(subject_type = 'document_artifact' "
            "AND document_artifact_id IS NOT NULL "
            "AND template_version_id IS NULL)",
            name="ck_document_external_edit_exactly_one_subject",
        ),
        sa.CheckConstraint(
            "status IN ('ready', 'changed', 'syncing', 'error')",
            name="ck_document_external_edit_status_valid",
        ),
        sa.CheckConstraint(
            "length(trim(provider)) > 0",
            name="ck_document_external_edit_provider_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(provider_connection_id)) > 0",
            name="ck_document_external_edit_connection_nonempty",
        ),
        sa.CheckConstraint(
            "length(base_checksum_sha256) = 64",
            name="ck_document_external_edit_checksum_length",
        ),
        sa.CheckConstraint(
            "active_sync_fingerprint IS NULL OR length(active_sync_fingerprint) = 64",
            name="ck_document_external_edit_active_fingerprint_length",
        ),
        sa.CheckConstraint(
            "last_sync_fingerprint IS NULL OR length(last_sync_fingerprint) = 64",
            name="ck_document_external_edit_last_fingerprint_length",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(
            ["template_version_id"],
            ["document_template_version.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_artifact_id"],
            ["document_artifact.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["last_imported_template_version_id"],
            ["document_template_version.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_staff_user_id"],
            ["staff_users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["last_synced_by_staff_user_id"],
            ["staff_users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_external_edit_session_tenant_id",
        "document_external_edit_session",
        ["tenant_id"],
    )
    op.create_index(
        "ix_document_external_edit_session_subject_type",
        "document_external_edit_session",
        ["subject_type"],
    )
    op.create_index(
        "ix_document_external_edit_session_template_version_id",
        "document_external_edit_session",
        ["template_version_id"],
    )
    op.create_index(
        "ix_document_external_edit_session_document_artifact_id",
        "document_external_edit_session",
        ["document_artifact_id"],
    )
    op.create_index(
        "ix_document_external_edit_session_status",
        "document_external_edit_session",
        ["status"],
    )
    op.create_index(
        "ix_document_external_edit_session_created_by_staff_user_id",
        "document_external_edit_session",
        ["created_by_staff_user_id"],
    )
    op.create_index(
        "ix_document_external_edit_session_last_synced_by_staff_user_id",
        "document_external_edit_session",
        ["last_synced_by_staff_user_id"],
    )
    op.create_index(
        "uq_document_external_edit_template_provider",
        "document_external_edit_session",
        ["tenant_id", "provider", "provider_connection_id", "template_version_id"],
        unique=True,
    )
    op.create_index(
        "uq_document_external_edit_artifact_provider",
        "document_external_edit_session",
        ["tenant_id", "provider", "provider_connection_id", "document_artifact_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("document_external_edit_session")
