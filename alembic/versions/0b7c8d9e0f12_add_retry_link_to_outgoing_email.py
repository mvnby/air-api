"""add retry link to outgoing_email

Revision ID: 0b7c8d9e0f12
Revises: f7a8b9c0d1e2
Create Date: 2026-07-08 16:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0b7c8d9e0f12"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("outgoing_email", sa.Column("retry_of_email_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_outgoing_email_retry_of_email_id"),
        "outgoing_email",
        ["retry_of_email_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_outgoing_email_retry_of_email_id_outgoing_email",
        "outgoing_email",
        "outgoing_email",
        ["retry_of_email_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_outgoing_email_retry_of_email_id_outgoing_email", "outgoing_email", type_="foreignkey")
    op.drop_index(op.f("ix_outgoing_email_retry_of_email_id"), table_name="outgoing_email")
    op.drop_column("outgoing_email", "retry_of_email_id")
