"""Add customer party identity and document signing city fields.

Revision ID: e8b9c0d1e2f3
Revises: e7a8b9c0d1e2
Create Date: 2026-08-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8b9c0d1e2f3"
down_revision: Union[str, None] = "e7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("customer") as batch_op:
        batch_op.add_column(sa.Column("city", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "signing_mode",
                sa.String(),
                nullable=False,
                server_default="self",
            )
        )

    bind.execute(
        sa.text(
            "UPDATE customer SET signing_mode = 'statutory_body' WHERE type = 'company'"
        )
    )

    with op.batch_alter_table("customer") as batch_op:
        batch_op.create_check_constraint(
            "ck_customer_signing_mode_valid",
            "signing_mode IN ('self', 'statutory_body', 'power_of_attorney')",
        )
        batch_op.alter_column("signing_mode", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("customer") as batch_op:
        batch_op.drop_constraint(
            "ck_customer_signing_mode_valid",
            type_="check",
        )
        batch_op.drop_column("signing_mode")
        batch_op.drop_column("city")
