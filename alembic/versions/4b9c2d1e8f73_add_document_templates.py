"""Add managed document templates

Revision ID: 4b9c2d1e8f73
Revises: 8f2a6d7c1b34
Create Date: 2026-05-06 07:45:00.000000

"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "4b9c2d1e8f73"
down_revision: Union[str, Sequence[str], None] = "8f2a6d7c1b34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_role_type(value: object) -> str:
    raw = str(value or "").strip()
    if raw in {"executor_customer", "contractor_customer"}:
        return raw
    return "seller_buyer"


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


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "document_template"):
        op.create_table(
            "document_template",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("doc_type", sa.String(), nullable=False),
            sa.Column("google_template_id", sa.String(), nullable=False),
            sa.Column("document_role_type", sa.String(), nullable=True),
            sa.Column("description", sa.String(), nullable=True),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("is_open_contract", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("client_restricted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    for index_name, columns in {
        "ix_document_template_name": ["name"],
        "ix_document_template_doc_type": ["doc_type"],
        "ix_document_template_google_template_id": ["google_template_id"],
        "ix_document_template_is_default": ["is_default"],
        "ix_document_template_is_active": ["is_active"],
        "ix_document_template_is_open_contract": ["is_open_contract"],
        "ix_document_template_client_restricted": ["client_restricted"],
        "ix_document_template_sort_order": ["sort_order"],
    }.items():
        _create_index_if_missing(inspector, "document_template", index_name, columns)

    if not _table_exists(inspector, "document_template_customer_link"):
        op.create_table(
            "document_template_customer_link",
            sa.Column("template_id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
            sa.ForeignKeyConstraint(["template_id"], ["document_template.id"]),
            sa.PrimaryKeyConstraint("template_id", "customer_id"),
        )
    if not _table_exists(inspector, "document_template_act_link"):
        op.create_table(
            "document_template_act_link",
            sa.Column("contract_template_id", sa.Integer(), nullable=False),
            sa.Column("act_template_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["act_template_id"], ["document_template.id"]),
            sa.ForeignKeyConstraint(["contract_template_id"], ["document_template.id"]),
            sa.PrimaryKeyConstraint("contract_template_id", "act_template_id"),
        )

    order_document_columns = _columns(inspector, "order_document")
    with op.batch_alter_table("order_document", schema=None) as batch_op:
        if "document_template_id" not in order_document_columns:
            batch_op.add_column(sa.Column("document_template_id", sa.Integer(), nullable=True))
        if "template_id" not in order_document_columns:
            batch_op.add_column(sa.Column("template_id", sa.String(), nullable=True))

    inspector = sa.inspect(bind)
    _create_index_if_missing(
        inspector,
        "order_document",
        "ix_order_document_document_template_id",
        ["document_template_id"],
    )
    _create_index_if_missing(inspector, "order_document", "ix_order_document_template_id", ["template_id"])
    fk_name = "fk_order_document_document_template_id_document_template"
    if fk_name not in _foreign_keys(inspector, "order_document"):
        with op.batch_alter_table("order_document", schema=None) as batch_op:
            batch_op.create_foreign_key(
                fk_name,
                "document_template",
                ["document_template_id"],
                ["id"],
            )

    row = bind.execute(
        text("SELECT value FROM global_config WHERE key = 'contract_templates' LIMIT 1")
    ).fetchone()
    if not row or not row[0]:
        return

    try:
        items = json.loads(row[0])
    except Exception:
        return
    if not isinstance(items, list):
        return

    now = datetime.now()
    template_table = sa.table(
        "document_template",
        sa.column("name", sa.String()),
        sa.column("doc_type", sa.String()),
        sa.column("google_template_id", sa.String()),
        sa.column("document_role_type", sa.String()),
        sa.column("is_default", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
        sa.column("is_open_contract", sa.Boolean()),
        sa.column("client_restricted", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    migrated = []
    seen: set[str] = set()
    existing_template_ids = {
        row[0]
        for row in bind.execute(text("SELECT google_template_id FROM document_template")).fetchall()
    }
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        google_template_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not google_template_id or google_template_id in seen or google_template_id in existing_template_ids:
            continue
        seen.add(google_template_id)
        migrated.append(
            {
                "name": name or google_template_id,
                "doc_type": "contract",
                "google_template_id": google_template_id,
                "document_role_type": _normalize_role_type(item.get("document_role_type")),
                "is_default": False,
                "is_active": True,
                "is_open_contract": bool(item.get("is_open_contract") is True),
                "client_restricted": False,
                "sort_order": index * 10,
                "created_at": now,
                "updated_at": now,
            }
        )
    if migrated:
        migrated[0]["is_default"] = True
        bind.execute(template_table.insert(), migrated)


def downgrade() -> None:
    with op.batch_alter_table("order_document", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_order_document_document_template_id_document_template"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_order_document_template_id"))
        batch_op.drop_index(batch_op.f("ix_order_document_document_template_id"))
        batch_op.drop_column("template_id")
        batch_op.drop_column("document_template_id")

    op.drop_table("document_template_act_link")
    op.drop_table("document_template_customer_link")
    with op.batch_alter_table("document_template", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_document_template_sort_order"))
        batch_op.drop_index(batch_op.f("ix_document_template_client_restricted"))
        batch_op.drop_index(batch_op.f("ix_document_template_is_open_contract"))
        batch_op.drop_index(batch_op.f("ix_document_template_is_active"))
        batch_op.drop_index(batch_op.f("ix_document_template_is_default"))
        batch_op.drop_index(batch_op.f("ix_document_template_google_template_id"))
        batch_op.drop_index(batch_op.f("ix_document_template_doc_type"))
        batch_op.drop_index(batch_op.f("ix_document_template_name"))
    op.drop_table("document_template")
