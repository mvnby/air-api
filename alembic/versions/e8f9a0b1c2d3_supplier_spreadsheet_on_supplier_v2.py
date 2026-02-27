"""supplier_spreadsheet_on_supplier_v2

Revision ID: e8f9a0b1c2d3
Revises: f0c1d2e3a4b5
Create Date: 2026-02-27 23:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, Sequence[str], None] = "f0c1d2e3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("supplier", sa.Column("spreadsheet_id", sa.String(), nullable=True))
    op.add_column("supplier", sa.Column("spreadsheet_url", sa.String(), nullable=True))
    op.add_column("supplier", sa.Column("google_sheet_synced_at", sa.DateTime(), nullable=True))
    op.create_index("ix_supplier_spreadsheet_id", "supplier", ["spreadsheet_id"], unique=False)

    # Backfill supplier.spreadsheet_id from the most recently updated source.
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT s.id, src.spreadsheet_id
            FROM supplier s
            LEFT JOIN LATERAL (
                SELECT spreadsheet_id
                FROM supplier_price_source x
                WHERE x.supplier_id = s.id
                  AND x.spreadsheet_id IS NOT NULL
                  AND x.spreadsheet_id <> ''
                ORDER BY x.updated_at DESC NULLS LAST, x.id DESC
                LIMIT 1
            ) src ON TRUE
            """
        )
    ).fetchall()
    for supplier_id, spreadsheet_id in rows:
        if spreadsheet_id:
            conn.execute(
                sa.text(
                    "UPDATE supplier SET spreadsheet_id = :sid WHERE id = :supplier_id"
                ),
                {"supplier_id": supplier_id, "sid": spreadsheet_id},
            )

    # Mark conflicting source spreadsheets for manual review.
    conflicts = conn.execute(
        sa.text(
            """
            SELECT supplier_id, COUNT(DISTINCT spreadsheet_id) AS cnt
            FROM supplier_price_source
            WHERE spreadsheet_id IS NOT NULL AND spreadsheet_id <> ''
            GROUP BY supplier_id
            HAVING COUNT(DISTINCT spreadsheet_id) > 1
            """
        )
    ).fetchall()
    for supplier_id, _cnt in conflicts:
        print(f"[alembic] supplier spreadsheet conflict: supplier_id={supplier_id}")
        conn.execute(
            sa.text(
                """
                UPDATE supplier_price_source
                SET last_sync_error = COALESCE(last_sync_error, '') ||
                    CASE
                        WHEN COALESCE(last_sync_error, '') = '' THEN ''
                        ELSE E'\n'
                    END ||
                    'Spreadsheet conflict after v2 migration: review supplier spreadsheet_id'
                WHERE supplier_id = :supplier_id
                """
            ),
            {"supplier_id": supplier_id},
        )

    op.alter_column("supplier_price_source", "spreadsheet_id", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    op.alter_column("supplier_price_source", "spreadsheet_id", existing_type=sa.String(), nullable=False)
    op.drop_index("ix_supplier_spreadsheet_id", table_name="supplier")
    op.drop_column("supplier", "google_sheet_synced_at")
    op.drop_column("supplier", "spreadsheet_url")
    op.drop_column("supplier", "spreadsheet_id")
