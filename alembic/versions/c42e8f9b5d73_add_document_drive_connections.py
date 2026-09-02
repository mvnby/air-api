"""Add tenant-owned Google Drive document connections.

Revision ID: c42e8f9b5d73
Revises: b31d9e7a4c62
Create Date: 2026-09-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c42e8f9b5d73"
down_revision: Union[str, None] = "b31d9e7a4c62"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_drive_connection",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("encrypted_credentials", sa.Text(), nullable=False),
        sa.Column("credentials_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("connection_key", sa.String(length=64), nullable=False),
        sa.Column("account_label", sa.String(length=320), nullable=True),
        sa.Column("managed_folder_id", sa.String(length=160), nullable=True),
        sa.Column("managed_folder_url", sa.String(length=1024), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_document_drive_connection_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_document_drive_connection_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            name="uq_document_drive_connection_tenant_provider",
        ),
    )
    op.create_index(
        "ix_document_drive_connection_tenant",
        "document_drive_connection",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_drive_connection_tenant",
        table_name="document_drive_connection",
    )
    op.drop_table("document_drive_connection")
