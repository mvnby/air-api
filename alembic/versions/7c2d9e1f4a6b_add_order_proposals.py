"""Add order proposals

Revision ID: 7c2d9e1f4a6b
Revises: 4b9c2d1e8f73
Create Date: 2026-05-06 15:30:00.000000

"""
from __future__ import annotations

from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "7c2d9e1f4a6b"
down_revision: Union[str, Sequence[str], None] = "4b9c2d1e8f73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _columns(inspector: sa.Inspector, table_name: str) -> set[str]:
    if not _table_exists(inspector, table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(inspector: sa.Inspector, table_name: str) -> set[str]:
    if not _table_exists(inspector, table_name):
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _foreign_keys(inspector: sa.Inspector, table_name: str) -> set[str]:
    if not _table_exists(inspector, table_name):
        return set()
    return {fk["name"] for fk in inspector.get_foreign_keys(table_name) if fk.get("name")}


def _create_index_if_missing(
    inspector: sa.Inspector,
    table_name: str,
    index_name: str,
    columns: list[str],
) -> None:
    if index_name in _indexes(inspector, table_name):
        return
    op.create_index(index_name, table_name, columns)


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if column.name in _columns(inspector, table_name):
        return
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.add_column(column)


def _create_fk_if_missing(
    table_name: str,
    fk_name: str,
    target_table: str,
    local_cols: list[str],
    remote_cols: list[str],
) -> None:
    inspector = sa.inspect(op.get_bind())
    if fk_name in _foreign_keys(inspector, table_name):
        return
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.create_foreign_key(fk_name, target_table, local_cols, remote_cols)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "order_proposal"):
        op.create_table(
            "order_proposal",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
            sa.Column("is_selected", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["order_id"], ["order.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    for index_name, columns in {
        "ix_order_proposal_order_id": ["order_id"],
        "ix_order_proposal_is_selected": ["is_selected"],
        "ix_order_proposal_is_archived": ["is_archived"],
        "ix_order_proposal_sort_order": ["sort_order"],
    }.items():
        _create_index_if_missing(inspector, "order_proposal", index_name, columns)

    _add_column_if_missing("order_product_link", sa.Column("proposal_id", sa.Integer(), nullable=True))
    _add_column_if_missing("order_service_link", sa.Column("proposal_id", sa.Integer(), nullable=True))

    inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "order_product_link", "ix_order_product_link_proposal_id", ["proposal_id"])
    _create_index_if_missing(inspector, "order_service_link", "ix_order_service_link_proposal_id", ["proposal_id"])
    _create_fk_if_missing(
        "order_product_link",
        "fk_order_product_link_proposal_id_order_proposal",
        "order_proposal",
        ["proposal_id"],
        ["id"],
    )
    _create_fk_if_missing(
        "order_service_link",
        "fk_order_service_link_proposal_id_order_proposal",
        "order_proposal",
        ["proposal_id"],
        ["id"],
    )

    order_ids = [
        row[0]
        for row in bind.execute(
            text(
                """
                SELECT o.id
                FROM "order" o
                LEFT JOIN order_proposal p ON p.order_id = o.id
                WHERE p.id IS NULL
                """
            )
        ).fetchall()
    ]
    if not order_ids:
        return

    proposal_table = sa.table(
        "order_proposal",
        sa.column("order_id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("status", sa.String()),
        sa.column("is_selected", sa.Boolean()),
        sa.column("is_archived", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    now = datetime.now()
    bind.execute(
        proposal_table.insert(),
        [
            {
                "order_id": order_id,
                "name": "Основное",
                "status": "draft",
                "is_selected": True,
                "is_archived": False,
                "sort_order": 0,
                "created_at": now,
                "updated_at": now,
            }
            for order_id in order_ids
        ],
    )
    bind.execute(
        text(
            """
            UPDATE order_product_link l
            SET proposal_id = p.id
            FROM order_proposal p
            WHERE l.order_id = p.order_id AND l.proposal_id IS NULL
            """
        )
    )
    bind.execute(
        text(
            """
            UPDATE order_service_link l
            SET proposal_id = p.id
            FROM order_proposal p
            WHERE l.order_id = p.order_id AND l.proposal_id IS NULL
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("order_service_link", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_order_service_link_proposal_id_order_proposal"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_order_service_link_proposal_id"))
        batch_op.drop_column("proposal_id")
    with op.batch_alter_table("order_product_link", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_order_product_link_proposal_id_order_proposal"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_order_product_link_proposal_id"))
        batch_op.drop_column("proposal_id")
    with op.batch_alter_table("order_proposal", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_order_proposal_sort_order"))
        batch_op.drop_index(batch_op.f("ix_order_proposal_is_archived"))
        batch_op.drop_index(batch_op.f("ix_order_proposal_is_selected"))
        batch_op.drop_index(batch_op.f("ix_order_proposal_order_id"))
    op.drop_table("order_proposal")
