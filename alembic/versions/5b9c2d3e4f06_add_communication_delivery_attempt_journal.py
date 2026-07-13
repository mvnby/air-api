"""add communication delivery attempt journal

Revision ID: 5b9c2d3e4f06
Revises: 4a8b1c2d3e05
Create Date: 2026-07-13 20:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5b9c2d3e4f06"
down_revision: Union[str, Sequence[str], None] = "4a8b1c2d3e05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "communication_delivery_attempt",
        sa.Column("delivery_id", sa.String(length=32), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("error_category", sa.String(length=80), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("retry_after_seconds", sa.BigInteger(), nullable=True),
        sa.Column("provider_latency_ms", sa.BigInteger(), nullable=True),
        sa.Column(
            "ambiguous",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_no > 0",
            name="ck_delivery_attempt_no_positive",
        ),
        sa.CheckConstraint(
            "outcome IN ('running', 'sent', 'retry', 'dead', 'canceled')",
            name="ck_delivery_attempt_outcome_valid",
        ),
        sa.CheckConstraint(
            "(outcome = 'running' AND finished_at IS NULL) "
            "OR (outcome <> 'running' AND finished_at IS NOT NULL)",
            name="ck_delivery_attempt_finish_state",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_delivery_attempt_finished_after_started",
        ),
        sa.CheckConstraint(
            "(outcome IN ('running', 'sent') AND error_category IS NULL "
            "AND error_code IS NULL) OR "
            "(outcome IN ('retry', 'dead', 'canceled') "
            "AND error_category IS NOT NULL AND length(trim(error_category)) > 0 "
            "AND error_code IS NOT NULL AND length(trim(error_code)) > 0)",
            name="ck_delivery_attempt_error_state",
        ),
        sa.CheckConstraint(
            "retry_after_seconds IS NULL OR retry_after_seconds > 0",
            name="ck_delivery_attempt_retry_after_positive",
        ),
        sa.CheckConstraint(
            "retry_after_seconds IS NULL OR outcome IN ('retry', 'dead')",
            name="ck_delivery_attempt_retry_after_state",
        ),
        sa.CheckConstraint(
            "provider_latency_ms IS NULL OR provider_latency_ms >= 0",
            name="ck_delivery_attempt_latency_non_negative",
        ),
        sa.CheckConstraint(
            "provider_latency_ms IS NULL OR outcome IN ('sent', 'retry', 'dead')",
            name="ck_delivery_attempt_latency_state",
        ),
        sa.CheckConstraint(
            "ambiguous = false OR outcome IN ('retry', 'dead')",
            name="ck_delivery_attempt_ambiguity_state",
        ),
        sa.ForeignKeyConstraint(
            ["delivery_id"],
            ["communication_delivery.delivery_id"],
            name="fk_delivery_attempt_delivery_id",
        ),
        sa.PrimaryKeyConstraint("delivery_id", "attempt_no"),
    )
    # A rolling deployment may observe a lease claimed by the dormant C1
    # worker before this migration is applied. Preserve that open attempt so
    # the C2 terminal/recovery paths can fence and finalize it normally rather
    # than repeatedly failing on a missing journal row.
    op.execute(
        sa.text(
            """
            INSERT INTO communication_delivery_attempt (
                delivery_id,
                attempt_no,
                started_at,
                finished_at,
                outcome,
                error_category,
                error_code,
                retry_after_seconds,
                provider_latency_ms,
                ambiguous
            )
            SELECT
                delivery_id,
                attempts,
                updated_at,
                NULL,
                'running',
                NULL,
                NULL,
                NULL,
                NULL,
                false
            FROM communication_delivery
            WHERE status = 'running'
            """
        )
    )
    op.create_index(
        "ix_delivery_attempt_outcome_started",
        "communication_delivery_attempt",
        ["outcome", "started_at"],
        unique=False,
    )
    op.create_index(
        "ix_delivery_attempt_error_finished",
        "communication_delivery_attempt",
        ["error_category", "error_code", "finished_at"],
        unique=False,
    )
    op.create_index(
        "ix_delivery_attempt_ambiguous_finished",
        "communication_delivery_attempt",
        ["finished_at"],
        unique=False,
        postgresql_where=sa.text("ambiguous = true"),
        sqlite_where=sa.text("ambiguous = 1"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_delivery_attempt_ambiguous_finished",
        table_name="communication_delivery_attempt",
    )
    op.drop_index(
        "ix_delivery_attempt_error_finished",
        table_name="communication_delivery_attempt",
    )
    op.drop_index(
        "ix_delivery_attempt_outcome_started",
        table_name="communication_delivery_attempt",
    )
    op.drop_table("communication_delivery_attempt")
