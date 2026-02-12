"""add lead table

Revision ID: b3c1f9a8d2e4
Revises: 9f7c1d2a4b10
Create Date: 2026-02-12 01:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3c1f9a8d2e4"
down_revision: Union[str, Sequence[str], None] = "9f7c1d2a4b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lead",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("segment_hint", sa.String(), nullable=False),
        sa.Column("loss_reason", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("inn", sa.String(), nullable=True),
        sa.Column("company_name", sa.String(), nullable=True),
        sa.Column("request_text", sa.String(), nullable=False),
        sa.Column("next_followup_date", sa.DateTime(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("converted_order_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["converted_order_id"], ["order.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lead_status", "lead", ["status"], unique=False)
    op.create_index("ix_lead_source", "lead", ["source"], unique=False)
    op.create_index("ix_lead_segment_hint", "lead", ["segment_hint"], unique=False)
    op.create_index("ix_lead_loss_reason", "lead", ["loss_reason"], unique=False)
    op.create_index("ix_lead_phone", "lead", ["phone"], unique=False)
    op.create_index("ix_lead_email", "lead", ["email"], unique=False)
    op.create_index("ix_lead_inn", "lead", ["inn"], unique=False)
    op.create_index("ix_lead_archived_at", "lead", ["archived_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_lead_archived_at", table_name="lead")
    op.drop_index("ix_lead_inn", table_name="lead")
    op.drop_index("ix_lead_email", table_name="lead")
    op.drop_index("ix_lead_phone", table_name="lead")
    op.drop_index("ix_lead_loss_reason", table_name="lead")
    op.drop_index("ix_lead_segment_hint", table_name="lead")
    op.drop_index("ix_lead_source", table_name="lead")
    op.drop_index("ix_lead_status", table_name="lead")
    op.drop_table("lead")
