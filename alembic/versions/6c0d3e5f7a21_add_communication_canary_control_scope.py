"""add communication canary control scope

Revision ID: 6c0d3e5f7a21
Revises: 5b9c2d4e6f10
Create Date: 2026-07-13 19:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "6c0d3e5f7a21"
down_revision: Union[str, Sequence[str], None] = "5b9c2d4e6f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("communication_runtime_state") as batch_op:
        batch_op.add_column(
            sa.Column("canary_run_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "control_revision",
                sa.BigInteger(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )

    # The previous runtime accepted ``canary`` only as a visible no-op and had
    # no run identity. Such a row cannot be safely inferred after this upgrade;
    # reset it to the fail-closed mode before enforcing the relational scope.
    op.execute(
        sa.text(
            "UPDATE communication_runtime_state "
            "SET mode = 'off', control_updated_at = CURRENT_TIMESTAMP, "
            "updated_at = CURRENT_TIMESTAMP WHERE mode = 'canary'"
        )
    )
    with op.batch_alter_table("communication_runtime_state") as batch_op:
        batch_op.create_check_constraint(
            "ck_communication_runtime_canary_scope_valid",
            "(mode = 'canary' AND canary_run_id IS NOT NULL "
            "AND length(canary_run_id) = 36) OR "
            "(mode IN ('off', 'all') AND canary_run_id IS NULL)",
        )
        batch_op.create_check_constraint(
            "ck_communication_runtime_control_revision_non_negative",
            "control_revision >= 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("communication_runtime_state") as batch_op:
        batch_op.drop_constraint(
            "ck_communication_runtime_control_revision_non_negative",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_communication_runtime_canary_scope_valid",
            type_="check",
        )
        batch_op.drop_column("control_revision")
        batch_op.drop_column("canary_run_id")
