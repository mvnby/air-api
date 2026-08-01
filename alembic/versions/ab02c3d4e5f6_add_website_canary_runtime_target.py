"""add website canary runtime target

Revision ID: ab02c3d4e5f6
Revises: aa91c2d4e6f8
Create Date: 2026-08-01 12:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "ab02c3d4e5f6"
down_revision: str | Sequence[str] | None = "aa91c2d4e6f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "communication_website_canary_run",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("storefront_id", sa.BigInteger(), nullable=False),
        sa.Column("recipient_key", sa.String(length=160), nullable=False),
        sa.Column("armed_control_revision", sa.BigInteger(), nullable=False),
        sa.Column(
            "state",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'armed'"),
        ),
        sa.Column("terminal_outcome", sa.String(length=16), nullable=True),
        sa.Column("terminal_control_revision", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(run_id) = 36",
            name="ck_communication_website_canary_run_id_valid",
        ),
        sa.CheckConstraint(
            "length(event_id) = 32",
            name="ck_communication_website_canary_event_id_valid",
        ),
        sa.CheckConstraint(
            "event_type IN ("
            "'crm.installation_estimate_lead.created', "
            "'tenant.website.checkout.created', "
            "'tenant.website.contact_lead.created', "
            "'tenant.website.product_availability.requested', "
            "'tenant.website.repair_diagnostic.created')",
            name="ck_communication_website_canary_event_type_valid",
        ),
        sa.CheckConstraint(
            "tenant_id > 0 AND storefront_id > 0",
            name="ck_communication_website_canary_scope_positive",
        ),
        sa.CheckConstraint(
            "length(trim(recipient_key)) > 0",
            name="ck_communication_website_canary_recipient_valid",
        ),
        sa.CheckConstraint(
            "armed_control_revision > 0",
            name="ck_communication_website_canary_armed_revision_positive",
        ),
        sa.CheckConstraint(
            "(state = 'armed' AND terminal_outcome IS NULL "
            "AND terminal_control_revision IS NULL AND finished_at IS NULL) "
            "OR (state = 'terminal' AND terminal_outcome IN ("
            "'sent', 'dead', 'canceled', 'ambiguous', 'aborted') "
            "AND terminal_control_revision > armed_control_revision "
            "AND finished_at IS NOT NULL)",
            name="ck_communication_website_canary_lifecycle_valid",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["integration_outbox_event.event_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("run_id"),
        sa.UniqueConstraint(
            "event_id",
            name="uq_communication_website_canary_run_event_id",
        ),
    )
    op.create_index(
        "ix_communication_website_canary_run_state_created",
        "communication_website_canary_run",
        ["state", "created_at"],
        unique=False,
    )
    with op.batch_alter_table("communication_runtime_state") as batch_op:
        batch_op.add_column(
            sa.Column(
                "canary_kind",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'operations'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "website_canary_run_id",
                sa.String(length=36),
                nullable=True,
            )
        )
        batch_op.create_check_constraint(
            "ck_communication_runtime_canary_kind_valid",
            "canary_kind IN ('operations', 'website')",
        )
        batch_op.create_check_constraint(
            "ck_communication_runtime_canary_reference_valid",
            "(canary_kind = 'operations' AND website_canary_run_id IS NULL) "
            "OR (canary_kind = 'website' AND mode = 'canary' "
            "AND website_canary_run_id IS NOT NULL "
            "AND website_canary_run_id = canary_run_id)",
        )
        batch_op.create_foreign_key(
            "fk_communication_runtime_website_canary_run",
            "communication_website_canary_run",
            ["website_canary_run_id"],
            ["run_id"],
        )


def downgrade() -> None:
    # An older runtime interprets every canary run as the operations canary.
    # Fence a website canary before removing the typed target columns.
    op.execute(
        sa.text(
            "UPDATE communication_runtime_state "
            "SET mode = 'off', canary_run_id = NULL, "
            "canary_kind = 'operations', website_canary_run_id = NULL, "
            "control_revision = control_revision + 1, "
            "control_updated_at = CURRENT_TIMESTAMP, "
            "updated_at = CURRENT_TIMESTAMP "
            "WHERE canary_kind = 'website'"
        )
    )
    with op.batch_alter_table("communication_runtime_state") as batch_op:
        batch_op.drop_constraint(
            "fk_communication_runtime_website_canary_run",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "ck_communication_runtime_canary_reference_valid",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_communication_runtime_canary_kind_valid",
            type_="check",
        )
        batch_op.drop_column("website_canary_run_id")
        batch_op.drop_column("canary_kind")
    op.drop_index(
        "ix_communication_website_canary_run_state_created",
        table_name="communication_website_canary_run",
    )
    op.drop_table("communication_website_canary_run")
