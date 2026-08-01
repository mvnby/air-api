"""Add tenant/storefront-scoped public write idempotency receipts.

Revision ID: aa91c2d4e6f8
Revises: e1f2a3b4c5d6
Create Date: 2026-08-01
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "aa91c2d4e6f8"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "public_write_idempotency",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("command_name", sa.String(length=80), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("resource_type", sa.String(length=40), nullable=True),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_public_write_idempotency_storefront_tenant",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "storefront_id",
            "command_name",
            "key_hash",
            name="uq_public_write_idempotency_scope_command_key",
        ),
    )
    op.create_index(
        "ix_public_write_idempotency_expires_at",
        "public_write_idempotency",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_public_write_idempotency_scope_created_at",
        "public_write_idempotency",
        ["tenant_id", "storefront_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_public_write_idempotency_expires_at",
        table_name="public_write_idempotency",
    )
    op.drop_index(
        "ix_public_write_idempotency_scope_created_at",
        table_name="public_write_idempotency",
    )
    op.drop_table("public_write_idempotency")
