"""add_customer_contracts

Revision ID: 9c2d1f8a7b64
Revises: 7d4e1a2b3c9f
Create Date: 2026-04-25 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "9c2d1f8a7b64"
down_revision: Union[str, Sequence[str], None] = "7d4e1a2b3c9f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("customer_contract"):
        op.create_table(
            "customer_contract",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("number", sa.String(), nullable=False),
            sa.Column("valid_from", sa.DateTime(), nullable=False),
            sa.Column("valid_until", sa.DateTime(), nullable=False),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("template_id", sa.String(), nullable=True),
            sa.Column("google_file_id", sa.String(), nullable=True),
            sa.Column("google_edit_url", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    index_names = {idx["name"] for idx in inspector.get_indexes("customer_contract")}
    for index_name, columns in (
        ("ix_customer_contract_customer_id", ["customer_id"]),
        ("ix_customer_contract_number", ["number"]),
        ("ix_customer_contract_status", ["status"]),
        ("ix_customer_contract_valid_from", ["valid_from"]),
        ("ix_customer_contract_valid_until", ["valid_until"]),
    ):
        if index_name not in index_names:
            op.create_index(index_name, "customer_contract", columns, unique=False)

    order_columns = {column["name"] for column in inspector.get_columns("order")}
    if "customer_contract_id" not in order_columns:
        with op.batch_alter_table("order", schema=None) as batch_op:
            batch_op.add_column(sa.Column("customer_contract_id", sa.Integer(), nullable=True))

    inspector = inspect(bind)
    order_fk_names = {fk["name"] for fk in inspector.get_foreign_keys("order")}
    order_index_names = {idx["name"] for idx in inspector.get_indexes("order")}
    with op.batch_alter_table("order", schema=None) as batch_op:
        if "fk_order_customer_contract_id_customer_contract" not in order_fk_names:
            batch_op.create_foreign_key(
                "fk_order_customer_contract_id_customer_contract",
                "customer_contract",
                ["customer_contract_id"],
                ["id"],
            )
        if "ix_order_customer_contract_id" not in order_index_names:
            batch_op.create_index("ix_order_customer_contract_id", ["customer_contract_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("order", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_order_customer_contract_id"))
        batch_op.drop_constraint("fk_order_customer_contract_id_customer_contract", type_="foreignkey")
        batch_op.drop_column("customer_contract_id")

    with op.batch_alter_table("customer_contract", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_customer_contract_valid_until"))
        batch_op.drop_index(batch_op.f("ix_customer_contract_valid_from"))
        batch_op.drop_index(batch_op.f("ix_customer_contract_status"))
        batch_op.drop_index(batch_op.f("ix_customer_contract_number"))
        batch_op.drop_index(batch_op.f("ix_customer_contract_customer_id"))

    op.drop_table("customer_contract")
