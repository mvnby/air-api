"""Expand staff users for manager auth

Revision ID: f6a7b8c9d0e2
Revises: e2b7c9d4a6f1
Create Date: 2026-06-12 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e2"
down_revision: Union[str, Sequence[str], None] = "e2b7c9d4a6f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _constraints(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {constraint["name"] for constraint in inspector.get_unique_constraints(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if column.name in _columns(table_name):
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(column)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if index_name not in _indexes(table_name):
        op.create_index(index_name, table_name, columns, unique=False)


def upgrade() -> None:
    _add_column_if_missing("staff_users", sa.Column("primary_role", sa.String(), nullable=True))
    _add_column_if_missing("staff_users", sa.Column("username", sa.String(), nullable=True))
    _add_column_if_missing("staff_users", sa.Column("password_hash", sa.String(), nullable=True))
    _add_column_if_missing("staff_users", sa.Column("telegram_username", sa.String(), nullable=True))
    _add_column_if_missing("staff_users", sa.Column("last_login_at", sa.DateTime(), nullable=True))

    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        conn.execute(
            sa.text(
                """
                UPDATE staff_users
                SET primary_role = CASE
                    WHEN roles::text LIKE '%owner%' OR roles::text LIKE '%admin%' THEN 'owner'
                    WHEN roles::text LIKE '%manager%' THEN 'manager'
                    ELSE 'installer'
                END
                WHERE primary_role IS NULL OR primary_role = ''
                """
            )
        )
    else:
        conn.execute(
            sa.text(
                """
                UPDATE staff_users
                SET primary_role = CASE
                    WHEN roles LIKE '%owner%' OR roles LIKE '%admin%' THEN 'owner'
                    WHEN roles LIKE '%manager%' THEN 'manager'
                    ELSE 'installer'
                END
                WHERE primary_role IS NULL OR primary_role = ''
                """
            )
        )

    with op.batch_alter_table("staff_users") as batch_op:
        batch_op.alter_column("primary_role", existing_type=sa.String(), nullable=False, server_default="installer")

    _create_index_if_missing("ix_staff_users_primary_role", "staff_users", ["primary_role"])
    _create_index_if_missing("ix_staff_users_telegram_username", "staff_users", ["telegram_username"])

    if "uq_staff_users_username" not in _constraints("staff_users"):
        with op.batch_alter_table("staff_users") as batch_op:
            batch_op.create_unique_constraint("uq_staff_users_username", ["username"])


def downgrade() -> None:
    with op.batch_alter_table("staff_users") as batch_op:
        if "uq_staff_users_username" in _constraints("staff_users"):
            batch_op.drop_constraint("uq_staff_users_username", type_="unique")

    if "ix_staff_users_telegram_username" in _indexes("staff_users"):
        op.drop_index("ix_staff_users_telegram_username", table_name="staff_users")
    if "ix_staff_users_primary_role" in _indexes("staff_users"):
        op.drop_index("ix_staff_users_primary_role", table_name="staff_users")

    existing_columns = _columns("staff_users")
    with op.batch_alter_table("staff_users") as batch_op:
        for column_name in ("last_login_at", "telegram_username", "password_hash", "username", "primary_role"):
            if column_name in existing_columns:
                batch_op.drop_column(column_name)
