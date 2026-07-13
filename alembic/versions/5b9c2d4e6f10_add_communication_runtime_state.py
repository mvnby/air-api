"""add communication runtime control and heartbeat state

Revision ID: 5b9c2d4e6f10
Revises: 5b9c2d3e4f06
Create Date: 2026-07-13 19:00:00.000000

"""

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "5b9c2d4e6f10"
down_revision: Union[str, Sequence[str], None] = "5b9c2d3e4f06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "communication_runtime_state",
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("instance_id", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("control_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(trim(channel)) > 0",
            name="ck_communication_runtime_channel_nonempty",
        ),
        sa.CheckConstraint(
            "mode IN ('off', 'canary', 'all')",
            name="ck_communication_runtime_mode_valid",
        ),
        sa.CheckConstraint(
            "status IN ('stopped', 'fencing', 'disabled', 'paused', "
            "'running', 'stopping', 'faulted')",
            name="ck_communication_runtime_status_valid",
        ),
        sa.PrimaryKeyConstraint("channel"),
    )
    op.create_index(
        "ix_communication_runtime_state_heartbeat_at",
        "communication_runtime_state",
        ["heartbeat_at"],
        unique=False,
    )

    now = datetime.now(timezone.utc)
    runtime_state = sa.table(
        "communication_runtime_state",
        sa.column("channel", sa.String),
        sa.column("mode", sa.String),
        sa.column("status", sa.String),
        sa.column("control_updated_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        runtime_state,
        [
            {
                "channel": "telegram",
                "mode": "off",
                "status": "stopped",
                "control_updated_at": now,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_communication_runtime_state_heartbeat_at",
        table_name="communication_runtime_state",
    )
    op.drop_table("communication_runtime_state")
