"""add immutable installation notification activation watermark

Revision ID: d8e7f6a5b4c3
Revises: f4d5e6f7a8b9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "d8e7f6a5b4c3"
down_revision: str | None = "f4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("communication_runtime_state") as batch_op:
        batch_op.add_column(
            sa.Column(
                "installation_estimate_watermark_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )

    # A legacy ``all`` row has no defensible cutover. Never infer one during
    # schema rollout: return it to the fail-closed mode and require the typed
    # activation command to perform a fresh safety transaction.
    op.execute(
        sa.text(
            "UPDATE communication_runtime_state "
            "SET mode = 'off', canary_run_id = NULL, "
            "control_revision = control_revision + 1, "
            "control_updated_at = CURRENT_TIMESTAMP, "
            "updated_at = CURRENT_TIMESTAMP "
            "WHERE mode = 'all'"
        )
    )

    with op.batch_alter_table("communication_runtime_state") as batch_op:
        batch_op.create_check_constraint(
            "ck_communication_runtime_all_watermark_required",
            "mode <> 'all' OR installation_estimate_watermark_at IS NOT NULL",
        )


def downgrade() -> None:
    # ``all`` cannot exist without the column that fences its event horizon.
    op.execute(
        sa.text(
            "UPDATE communication_runtime_state "
            "SET mode = 'off', canary_run_id = NULL, "
            "control_revision = control_revision + 1, "
            "control_updated_at = CURRENT_TIMESTAMP, "
            "updated_at = CURRENT_TIMESTAMP "
            "WHERE mode = 'all'"
        )
    )
    with op.batch_alter_table("communication_runtime_state") as batch_op:
        batch_op.drop_constraint(
            "ck_communication_runtime_all_watermark_required",
            type_="check",
        )
        batch_op.drop_column("installation_estimate_watermark_at")
