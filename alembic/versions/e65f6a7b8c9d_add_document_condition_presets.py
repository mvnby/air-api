"""Add tenant-scoped reusable document conditions.

Revision ID: e65f6a7b8c9d
Revises: e64f5a6b7c8d
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e65f6a7b8c9d"
down_revision: str | None = "e64f5a6b7c8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "document_condition_preset",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("text", sa.String(1000), nullable=False),
        sa.Column("normalized_text", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(text)) > 0", name="ck_document_condition_preset_text_nonempty"),
        sa.UniqueConstraint("tenant_id", "normalized_text", name="uq_document_condition_preset_tenant_text"),
    )
    op.create_index("ix_document_condition_preset_tenant_id", "document_condition_preset", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_document_condition_preset_tenant_id", table_name="document_condition_preset")
    op.drop_table("document_condition_preset")
