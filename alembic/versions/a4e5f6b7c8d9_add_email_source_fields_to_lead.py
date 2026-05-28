"""add_email_source_fields_to_lead

Revision ID: a4e5f6b7c8d9
Revises: 9a3f6b8c1d2e
Create Date: 2026-05-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "a4e5f6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "9a3f6b8c1d2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    columns = _columns("lead")
    with op.batch_alter_table("lead", schema=None) as batch_op:
        if "source_message_id" not in columns:
            batch_op.add_column(sa.Column("source_message_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        if "source_fingerprint" not in columns:
            batch_op.add_column(sa.Column("source_fingerprint", sqlmodel.sql.sqltypes.AutoString(), nullable=True))

    indexes = _indexes("lead")
    if "ix_lead_source_message_id" not in indexes:
        op.create_index("ix_lead_source_message_id", "lead", ["source_message_id"], unique=False)
    if "ix_lead_source_fingerprint" not in indexes:
        op.create_index("ix_lead_source_fingerprint", "lead", ["source_fingerprint"], unique=False)


def downgrade() -> None:
    indexes = _indexes("lead")
    if "ix_lead_source_fingerprint" in indexes:
        op.drop_index("ix_lead_source_fingerprint", table_name="lead")
    if "ix_lead_source_message_id" in indexes:
        op.drop_index("ix_lead_source_message_id", table_name="lead")

    columns = _columns("lead")
    with op.batch_alter_table("lead", schema=None) as batch_op:
        if "source_fingerprint" in columns:
            batch_op.drop_column("source_fingerprint")
        if "source_message_id" in columns:
            batch_op.drop_column("source_message_id")
