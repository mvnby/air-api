"""add document seller entity type

Revision ID: e7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-08-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ENTITY_TYPE_CHECK = "entity_type IN ('organization', 'individual_entrepreneur')"


def upgrade() -> None:
    op.add_column(
        "document_legal_entity",
        sa.Column(
            "entity_type",
            sa.String(length=32),
            nullable=False,
            server_default="organization",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE document_legal_entity "
            "SET entity_type = 'individual_entrepreneur' "
            "WHERE display_name LIKE 'ИП %' "
            "OR display_name LIKE 'ип %' "
            "OR display_name LIKE 'Индивидуальный предприниматель%' "
            "OR legal_name LIKE 'ИП %' "
            "OR legal_name LIKE 'ип %' "
            "OR legal_name LIKE 'Индивидуальный предприниматель%'"
        )
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("document_legal_entity") as batch_op:
            batch_op.create_check_constraint(
                "ck_document_legal_entity_type_valid",
                ENTITY_TYPE_CHECK,
            )
    else:
        op.create_check_constraint(
            "ck_document_legal_entity_type_valid",
            "document_legal_entity",
            ENTITY_TYPE_CHECK,
        )
    op.create_index(
        "ix_document_legal_entity_entity_type",
        "document_legal_entity",
        ["entity_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_legal_entity_entity_type",
        table_name="document_legal_entity",
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("document_legal_entity") as batch_op:
            batch_op.drop_constraint(
                "ck_document_legal_entity_type_valid",
                type_="check",
            )
            batch_op.drop_column("entity_type")
    else:
        op.drop_constraint(
            "ck_document_legal_entity_type_valid",
            "document_legal_entity",
            type_="check",
        )
        op.drop_column("document_legal_entity", "entity_type")
