"""add durable communication provider-call boundary

Revision ID: e9a1b2c3d4e5
Revises: d8e7f6a5b4c3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e9a1b2c3d4e5"
down_revision: str | None = "d8e7f6a5b4c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("communication_delivery_attempt") as batch_op:
        batch_op.add_column(
            sa.Column(
                "provider_started_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.create_check_constraint(
            "ck_delivery_attempt_provider_after_started",
            "provider_started_at IS NULL "
            "OR provider_started_at >= started_at",
        )
        batch_op.create_check_constraint(
            "ck_delivery_attempt_provider_before_finished",
            "provider_started_at IS NULL OR finished_at IS NULL "
            "OR provider_started_at <= finished_at",
        )

    # An old worker may already have crossed Telegram's acceptance boundary.
    # Conservatively mark every in-flight legacy attempt before new recovery
    # logic is allowed to classify a NULL boundary as retry-safe.
    op.execute(
        sa.text(
            "UPDATE communication_delivery_attempt "
            "SET provider_started_at = started_at "
            "WHERE outcome = 'running' AND provider_started_at IS NULL"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("communication_delivery_attempt") as batch_op:
        batch_op.drop_constraint(
            "ck_delivery_attempt_provider_before_finished",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_delivery_attempt_provider_after_started",
            type_="check",
        )
        batch_op.drop_column("provider_started_at")
