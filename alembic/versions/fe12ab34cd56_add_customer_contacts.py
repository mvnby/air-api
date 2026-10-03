"""Add customer contacts and contact change history.

Revision ID: fe12ab34cd56
Revises: fc2d3e4f5a6b
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "fe12ab34cd56"
down_revision: Union[str, Sequence[str], None] = "fc2d3e4f5a6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_contact",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("role", sa.String(length=120), nullable=True),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_legacy", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_contact_customer_id", "customer_contact", ["customer_id"])
    op.create_index("ix_customer_contact_customer_active", "customer_contact", ["customer_id", "is_active"])
    op.create_index(
        "uq_customer_contact_primary",
        "customer_contact",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
        sqlite_where=sa.text("is_primary = 1"),
    )

    op.create_table(
        "customer_contact_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=True),
        sa.Column("field_name", sa.String(length=40), nullable=False),
        sa.Column("old_value", sa.String(), nullable=True),
        sa.Column("new_value", sa.String(), nullable=True),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("author_name", sa.String(length=160), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["customer_contact.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["author_id"], ["staff_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_contact_history_customer_id", "customer_contact_history", ["customer_id"])
    op.create_index("ix_customer_contact_history_contact_id", "customer_contact_history", ["contact_id"])
    op.create_index(
        "ix_customer_contact_history_customer_changed",
        "customer_contact_history",
        ["customer_id", "changed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_customer_contact_history_customer_changed", table_name="customer_contact_history")
    op.drop_index("ix_customer_contact_history_contact_id", table_name="customer_contact_history")
    op.drop_index("ix_customer_contact_history_customer_id", table_name="customer_contact_history")
    op.drop_table("customer_contact_history")
    op.drop_index("uq_customer_contact_primary", table_name="customer_contact")
    op.drop_index("ix_customer_contact_customer_active", table_name="customer_contact")
    op.drop_index("ix_customer_contact_customer_id", table_name="customer_contact")
    op.drop_table("customer_contact")
