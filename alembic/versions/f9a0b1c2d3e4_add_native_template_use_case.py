"""Add native document template use-case metadata.

Revision ID: f9a0b1c2d3e4
Revises: e8b9c0d1e2f3
Create Date: 2026-08-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, None] = "e8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("document_template") as batch_op:
        batch_op.add_column(sa.Column("contract_scenario", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("business_role", sa.String(32), nullable=True))
        batch_op.create_check_constraint(
            "ck_document_template_contract_scenario_valid",
            "contract_scenario IS NULL OR contract_scenario IN "
            "('services', 'repair', 'maintenance', 'supply_installation', "
            "'installation', 'framework', 'supply')",
        )
        batch_op.create_check_constraint(
            "ck_document_template_business_role_valid",
            "business_role IS NULL OR business_role IN ('payment_request', 'offer')",
        )
        batch_op.create_check_constraint(
            "ck_document_template_contract_scenario_scope",
            "contract_scenario IS NULL OR doc_type = 'contract'",
        )
        batch_op.create_check_constraint(
            "ck_document_template_business_role_scope",
            "business_role IS NULL OR doc_type = 'invoice'",
        )
        batch_op.create_index(
            "ix_document_template_contract_scenario", ["contract_scenario"]
        )
        batch_op.create_index("ix_document_template_business_role", ["business_role"])


def downgrade() -> None:
    with op.batch_alter_table("document_template") as batch_op:
        batch_op.drop_index("ix_document_template_business_role")
        batch_op.drop_index("ix_document_template_contract_scenario")
        batch_op.drop_constraint(
            "ck_document_template_business_role_scope", type_="check"
        )
        batch_op.drop_constraint(
            "ck_document_template_contract_scenario_scope", type_="check"
        )
        batch_op.drop_constraint(
            "ck_document_template_business_role_valid", type_="check"
        )
        batch_op.drop_constraint(
            "ck_document_template_contract_scenario_valid", type_="check"
        )
        batch_op.drop_column("business_role")
        batch_op.drop_column("contract_scenario")
