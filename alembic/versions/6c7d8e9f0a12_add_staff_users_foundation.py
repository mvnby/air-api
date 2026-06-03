"""Add staff users foundation

Revision ID: 6c7d8e9f0a12
Revises: 5a6b7c8d9e10
Create Date: 2026-06-03 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6c7d8e9f0a12"
down_revision: Union[str, Sequence[str], None] = "5a6b7c8d9e10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def upgrade() -> None:
    if "staff_users" not in _tables():
        op.create_table(
            "staff_users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("display_name", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("roles", sa.JSON(), nullable=False),
            sa.Column("phone", sa.String(), nullable=True),
            sa.Column("email", sa.String(), nullable=True),
            sa.Column("telegram_id", sa.BigInteger(), nullable=True),
            sa.Column("legacy_installer_id", sa.Integer(), nullable=True),
            sa.Column("default_rate", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["legacy_installer_id"], ["installers.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("telegram_id", name="uq_staff_users_telegram_id"),
            sa.UniqueConstraint("legacy_installer_id", name="uq_staff_users_legacy_installer_id"),
        )
        op.create_index("ix_staff_users_display_name", "staff_users", ["display_name"], unique=False)
        op.create_index("ix_staff_users_status", "staff_users", ["status"], unique=False)
        op.create_index("ix_staff_users_phone", "staff_users", ["phone"], unique=False)
        op.create_index("ix_staff_users_email", "staff_users", ["email"], unique=False)
        op.create_index("ix_staff_users_legacy_installer_id", "staff_users", ["legacy_installer_id"], unique=False)

    conn = op.get_bind()
    roles_expr = """'["installer"]'::json""" if conn.dialect.name == "postgresql" else """'["installer"]'"""
    conn.execute(
        sa.text(
            f"""
            INSERT INTO staff_users (
                display_name,
                status,
                roles,
                telegram_id,
                legacy_installer_id,
                default_rate,
                created_at,
                updated_at
            )
            SELECT
                i.name,
                CASE WHEN i.is_active THEN 'active' ELSE 'inactive' END,
                {roles_expr},
                i.telegram_id,
                i.id,
                i.default_rate,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM installers i
            WHERE NOT EXISTS (
                SELECT 1
                FROM staff_users su
                WHERE su.legacy_installer_id = i.id
            )
            """
        )
    )


def downgrade() -> None:
    if "staff_users" in _tables():
        op.drop_index("ix_staff_users_legacy_installer_id", table_name="staff_users")
        op.drop_index("ix_staff_users_email", table_name="staff_users")
        op.drop_index("ix_staff_users_phone", table_name="staff_users")
        op.drop_index("ix_staff_users_status", table_name="staff_users")
        op.drop_index("ix_staff_users_display_name", table_name="staff_users")
        op.drop_table("staff_users")
