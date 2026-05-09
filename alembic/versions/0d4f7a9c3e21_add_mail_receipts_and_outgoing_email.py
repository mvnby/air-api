"""add mail receipts and outgoing email

Revision ID: 0d4f7a9c3e21
Revises: 8e4f2a1c9b7d
Create Date: 2026-05-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "0d4f7a9c3e21"
down_revision: Union[str, Sequence[str], None] = "8e4f2a1c9b7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if index_name not in _indexes(table_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    if not _has_table("bank_receipt"):
        op.create_table(
            "bank_receipt",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("operation_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("sender_email", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("subject", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("message_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("fingerprint", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("email_date", sa.DateTime(), nullable=True),
            sa.Column("received_at", sa.DateTime(), nullable=True),
            sa.Column("our_account", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="BYN"),
            sa.Column("payer_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("payer_unp", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("payer_account", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("payment_document_raw", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("payment_document_number", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("payment_purpose", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("account_balance_after", sa.Float(), nullable=True),
            sa.Column("raw_body", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("parse_error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("matched_order_id", sa.Integer(), nullable=True),
            sa.Column("matched_payment_id", sa.Integer(), nullable=True),
            sa.Column("match_meta", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["matched_order_id"], ["order.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(op.f("ix_bank_receipt_account_balance_after"), "bank_receipt", ["account_balance_after"])
    _create_index_if_missing(op.f("ix_bank_receipt_amount"), "bank_receipt", ["amount"])
    _create_index_if_missing(op.f("ix_bank_receipt_email_date"), "bank_receipt", ["email_date"])
    _create_index_if_missing(op.f("ix_bank_receipt_fingerprint"), "bank_receipt", ["fingerprint"], unique=True)
    _create_index_if_missing(op.f("ix_bank_receipt_matched_order_id"), "bank_receipt", ["matched_order_id"])
    _create_index_if_missing(op.f("ix_bank_receipt_matched_payment_id"), "bank_receipt", ["matched_payment_id"])
    _create_index_if_missing(op.f("ix_bank_receipt_message_id"), "bank_receipt", ["message_id"], unique=True)
    _create_index_if_missing(op.f("ix_bank_receipt_operation_type"), "bank_receipt", ["operation_type"])
    _create_index_if_missing(op.f("ix_bank_receipt_our_account"), "bank_receipt", ["our_account"])
    _create_index_if_missing(op.f("ix_bank_receipt_payer_account"), "bank_receipt", ["payer_account"])
    _create_index_if_missing(op.f("ix_bank_receipt_payer_name"), "bank_receipt", ["payer_name"])
    _create_index_if_missing(op.f("ix_bank_receipt_payer_unp"), "bank_receipt", ["payer_unp"])
    _create_index_if_missing(op.f("ix_bank_receipt_payment_document_number"), "bank_receipt", ["payment_document_number"])
    _create_index_if_missing(op.f("ix_bank_receipt_received_at"), "bank_receipt", ["received_at"])
    _create_index_if_missing(op.f("ix_bank_receipt_sender_email"), "bank_receipt", ["sender_email"])
    _create_index_if_missing(op.f("ix_bank_receipt_status"), "bank_receipt", ["status"])

    if not _has_table("outgoing_email"):
        op.create_table(
            "outgoing_email",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("order_id", sa.Integer(), nullable=True),
            sa.Column("customer_id", sa.Integer(), nullable=True),
            sa.Column("recipient_email", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("subject", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("body_text", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("body_html", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("from_email", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("from_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("reply_to", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("attachments", sa.JSON(), nullable=True),
            sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
            sa.ForeignKeyConstraint(["order_id"], ["order.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(op.f("ix_outgoing_email_customer_id"), "outgoing_email", ["customer_id"])
    _create_index_if_missing(op.f("ix_outgoing_email_order_id"), "outgoing_email", ["order_id"])
    _create_index_if_missing(op.f("ix_outgoing_email_recipient_email"), "outgoing_email", ["recipient_email"])
    _create_index_if_missing(op.f("ix_outgoing_email_sent_at"), "outgoing_email", ["sent_at"])
    _create_index_if_missing(op.f("ix_outgoing_email_status"), "outgoing_email", ["status"])

    if "bank_receipt_id" not in _columns("payment"):
        with op.batch_alter_table("payment", schema=None) as batch_op:
            batch_op.add_column(sa.Column("bank_receipt_id", sa.Integer(), nullable=True))
            batch_op.create_index(batch_op.f("ix_payment_bank_receipt_id"), ["bank_receipt_id"], unique=False)
            batch_op.create_foreign_key("fk_payment_bank_receipt_id_bank_receipt", "bank_receipt", ["bank_receipt_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("payment", schema=None) as batch_op:
        batch_op.drop_constraint("fk_payment_bank_receipt_id_bank_receipt", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_payment_bank_receipt_id"))
        batch_op.drop_column("bank_receipt_id")

    op.drop_index(op.f("ix_outgoing_email_status"), table_name="outgoing_email")
    op.drop_index(op.f("ix_outgoing_email_sent_at"), table_name="outgoing_email")
    op.drop_index(op.f("ix_outgoing_email_recipient_email"), table_name="outgoing_email")
    op.drop_index(op.f("ix_outgoing_email_order_id"), table_name="outgoing_email")
    op.drop_index(op.f("ix_outgoing_email_customer_id"), table_name="outgoing_email")
    op.drop_table("outgoing_email")

    op.drop_index(op.f("ix_bank_receipt_status"), table_name="bank_receipt")
    op.drop_index(op.f("ix_bank_receipt_sender_email"), table_name="bank_receipt")
    op.drop_index(op.f("ix_bank_receipt_received_at"), table_name="bank_receipt")
    op.drop_index(op.f("ix_bank_receipt_payment_document_number"), table_name="bank_receipt")
    op.drop_index(op.f("ix_bank_receipt_payer_unp"), table_name="bank_receipt")
    op.drop_index(op.f("ix_bank_receipt_payer_name"), table_name="bank_receipt")
    op.drop_index(op.f("ix_bank_receipt_payer_account"), table_name="bank_receipt")
    op.drop_index(op.f("ix_bank_receipt_our_account"), table_name="bank_receipt")
    op.drop_index(op.f("ix_bank_receipt_operation_type"), table_name="bank_receipt")
    op.drop_index(op.f("ix_bank_receipt_message_id"), table_name="bank_receipt")
    op.drop_index(op.f("ix_bank_receipt_matched_payment_id"), table_name="bank_receipt")
    op.drop_index(op.f("ix_bank_receipt_matched_order_id"), table_name="bank_receipt")
    op.drop_index(op.f("ix_bank_receipt_fingerprint"), table_name="bank_receipt")
    op.drop_index(op.f("ix_bank_receipt_email_date"), table_name="bank_receipt")
    op.drop_index(op.f("ix_bank_receipt_amount"), table_name="bank_receipt")
    op.drop_index(op.f("ix_bank_receipt_account_balance_after"), table_name="bank_receipt")
    op.drop_table("bank_receipt")
