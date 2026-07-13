"""normalize legacy PostgreSQL columns to current metadata

Revision ID: 2d4f6a8b0c13
Revises: 1c3e5a7b9d02
Create Date: 2026-07-13 00:00:00.000000

Fresh databases already receive ``VARCHAR`` from the repaired pre-Alembic
baseline. Databases that applied the historical a55 revision before that
repair still have the native ``customertype`` enum, so this forward migration
converges both upgrade paths without rewriting already-correct installations.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "2d4f6a8b0c13"
down_revision: Union[str, Sequence[str], None] = "1c3e5a7b9d02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _postgres_column_udt() -> str | None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return None
    return bind.execute(
        sa.text(
            """
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'customer'
              AND column_name = 'type'
            """
        )
    ).scalar_one_or_none()


def _postgres_type_exists(type_name: str) -> bool:
    return bool(
        op.get_bind().execute(
            sa.text("SELECT 1 FROM pg_type WHERE typname = :type_name"),
            {"type_name": type_name},
        ).scalar_one_or_none()
    )


def _postgres_type_usage_count(type_name: str) -> int:
    return int(
        op.get_bind().execute(
            sa.text(
                """
                SELECT count(*)
                FROM pg_attribute attribute
                JOIN pg_type type ON type.oid = attribute.atttypid
                WHERE type.typname = :type_name
                  AND attribute.attnum > 0
                  AND NOT attribute.attisdropped
                """
            ),
            {"type_name": type_name},
        ).scalar_one()
    )


def _postgres_column_is_nullable(table_name: str, column_name: str) -> bool | None:
    if op.get_bind().dialect.name != "postgresql":
        return None
    value = op.get_bind().execute(
        sa.text(
            """
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).scalar_one_or_none()
    return value == "YES" if value is not None else None


def upgrade() -> None:
    if _postgres_column_udt() == "customertype":
        op.execute('ALTER TABLE customer ALTER COLUMN type DROP DEFAULT')
        op.execute('ALTER TABLE customer ALTER COLUMN type TYPE VARCHAR USING type::text')
        op.execute("ALTER TABLE customer ALTER COLUMN type SET DEFAULT 'individual'")
        if _postgres_type_usage_count("customertype") == 0:
            op.execute("DROP TYPE customertype")

    if _postgres_column_is_nullable("order", "status"):
        # NULL was never a valid workflow state. Older databases allowed it
        # because the first migration inherited SQLite-era nullability.
        op.execute("UPDATE \"order\" SET status = 'new_lead' WHERE status IS NULL")
        op.alter_column("order", "status", existing_type=sa.String(), nullable=False)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    if _postgres_column_is_nullable("order", "status") is False:
        op.alter_column("order", "status", existing_type=sa.String(), nullable=True)

    if _postgres_column_udt() == "varchar":
        if not _postgres_type_exists("customertype"):
            op.execute("CREATE TYPE customertype AS ENUM ('individual', 'company')")
        op.execute("ALTER TABLE customer ALTER COLUMN type DROP DEFAULT")
        op.execute(
            "ALTER TABLE customer ALTER COLUMN type TYPE customertype "
            "USING type::customertype"
        )
        op.execute("ALTER TABLE customer ALTER COLUMN type SET DEFAULT 'individual'")
