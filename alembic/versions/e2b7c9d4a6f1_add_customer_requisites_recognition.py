"""add customer requisites recognition

Revision ID: e2b7c9d4a6f1
Revises: 7d1e9c4a2f63
Create Date: 2026-06-12 14:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e2b7c9d4a6f1"
down_revision: Union[str, Sequence[str], None] = "7d1e9c4a2f63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_requisites_recognition",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("telegram_user_id", sa.Integer(), nullable=True),
        sa.Column("telegram_chat_id", sa.Integer(), nullable=True),
        sa.Column("telegram_message_id", sa.Integer(), nullable=True),
        sa.Column("original_filename", sa.String(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("local_file_path", sa.String(), nullable=True),
        sa.Column("local_file_url", sa.String(), nullable=True),
        sa.Column("raw_text", sa.String(), nullable=False),
        sa.Column("extracted_json", sa.JSON(), nullable=False),
        sa.Column("validation_flags", sa.JSON(), nullable=False),
        sa.Column("duplicate_customer_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_customer_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_action", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["confirmed_customer_id"], ["customer.id"]),
        sa.ForeignKeyConstraint(["duplicate_customer_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_requisites_recognition_created_at", "customer_requisites_recognition", ["created_at"])
    op.create_index("ix_customer_requisites_recognition_source", "customer_requisites_recognition", ["source"])
    op.create_index("ix_customer_requisites_recognition_status", "customer_requisites_recognition", ["status"])
    op.create_index(
        "ix_customer_requisites_recognition_telegram_user_id",
        "customer_requisites_recognition",
        ["telegram_user_id"],
    )
    op.create_index(
        "ix_customer_requisites_recognition_telegram_chat_id",
        "customer_requisites_recognition",
        ["telegram_chat_id"],
    )
    op.create_index(
        "ix_customer_requisites_recognition_telegram_message_id",
        "customer_requisites_recognition",
        ["telegram_message_id"],
    )
    op.create_index(
        "ix_customer_requisites_recognition_duplicate_customer_id",
        "customer_requisites_recognition",
        ["duplicate_customer_id"],
    )
    op.create_index(
        "ix_customer_requisites_recognition_confirmed_customer_id",
        "customer_requisites_recognition",
        ["confirmed_customer_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_customer_requisites_recognition_confirmed_customer_id", table_name="customer_requisites_recognition")
    op.drop_index("ix_customer_requisites_recognition_duplicate_customer_id", table_name="customer_requisites_recognition")
    op.drop_index("ix_customer_requisites_recognition_telegram_message_id", table_name="customer_requisites_recognition")
    op.drop_index("ix_customer_requisites_recognition_telegram_chat_id", table_name="customer_requisites_recognition")
    op.drop_index("ix_customer_requisites_recognition_telegram_user_id", table_name="customer_requisites_recognition")
    op.drop_index("ix_customer_requisites_recognition_status", table_name="customer_requisites_recognition")
    op.drop_index("ix_customer_requisites_recognition_source", table_name="customer_requisites_recognition")
    op.drop_index("ix_customer_requisites_recognition_created_at", table_name="customer_requisites_recognition")
    op.drop_table("customer_requisites_recognition")
