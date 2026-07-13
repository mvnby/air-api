"""harden communication delivery lease state

Revision ID: 4a8b1c2d3e05
Revises: 3f7a9c1d2e04
Create Date: 2026-07-13 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "4a8b1c2d3e05"
down_revision: Union[str, Sequence[str], None] = "3f7a9c1d2e04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("communication_delivery") as batch_op:
        batch_op.create_check_constraint(
            "ck_delivery_attempts_within_max",
            "attempts <= max_attempts",
        )
        batch_op.create_check_constraint(
            "ck_delivery_active_attempts_remaining",
            "status NOT IN ('queued', 'retry') OR attempts < max_attempts",
        )
        batch_op.create_check_constraint(
            "ck_delivery_lease_state",
            "(status = 'running' AND worker_id IS NOT NULL "
            "AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR (status <> 'running' AND worker_id IS NULL "
            "AND lease_token IS NULL AND lease_expires_at IS NULL)",
        )
        batch_op.create_check_constraint(
            "ck_delivery_terminal_timestamps",
            "(status = 'sent' AND sent_at IS NOT NULL AND finished_at IS NOT NULL) "
            "OR (status IN ('dead', 'canceled') AND sent_at IS NULL "
            "AND finished_at IS NOT NULL) "
            "OR (status IN ('queued', 'running', 'retry') AND sent_at IS NULL "
            "AND finished_at IS NULL)",
        )
        batch_op.create_check_constraint(
            "ck_delivery_attempt_phase",
            "(status = 'queued' AND attempts = 0) "
            "OR (status IN ('running', 'retry', 'sent', 'dead', 'canceled') "
            "AND attempts >= 1)",
        )
        batch_op.create_check_constraint(
            "ck_delivery_provider_message_state",
            "(status = 'sent' AND provider_message_id IS NOT NULL "
            "AND length(trim(provider_message_id)) > 0) "
            "OR (status <> 'sent' AND provider_message_id IS NULL)",
        )

    op.create_index(
        "ix_communication_delivery_channel_claim",
        "communication_delivery",
        ["channel", "priority", "available_at", "created_at", "delivery_id"],
        unique=False,
        postgresql_where=sa.text("status IN ('queued', 'retry')"),
    )
    op.create_index(
        "ix_communication_delivery_channel_recovery",
        "communication_delivery",
        ["channel", "lease_expires_at", "created_at", "delivery_id"],
        unique=False,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_communication_delivery_channel_recovery",
        table_name="communication_delivery",
    )
    op.drop_index(
        "ix_communication_delivery_channel_claim",
        table_name="communication_delivery",
    )
    with op.batch_alter_table("communication_delivery") as batch_op:
        batch_op.drop_constraint(
            "ck_delivery_provider_message_state",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_delivery_attempt_phase",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_delivery_terminal_timestamps",
            type_="check",
        )
        batch_op.drop_constraint("ck_delivery_lease_state", type_="check")
        batch_op.drop_constraint(
            "ck_delivery_attempts_within_max",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_delivery_active_attempts_remaining",
            type_="check",
        )
