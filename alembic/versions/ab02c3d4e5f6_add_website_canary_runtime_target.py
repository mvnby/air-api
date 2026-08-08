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


CANARY_TRIGGER = "trg_communication_website_canary_run_immutable"
CANARY_FUNCTION = "fn_communication_website_canary_run_immutable"
BACKLOG_TRIGGER = "trg_communication_website_backlog_operation_immutable"
BACKLOG_FUNCTION = "fn_communication_website_backlog_operation_immutable"


def _create_postgresql_immutability_triggers() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {CANARY_FUNCTION}()
            RETURNS trigger AS $function$
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    IF NEW.state IS DISTINCT FROM 'armed'
                       OR NEW.terminal_outcome IS NOT NULL
                       OR NEW.terminal_control_revision IS NOT NULL
                       OR NEW.finished_at IS NOT NULL THEN
                        RAISE EXCEPTION 'communication_website_canary_run_immutable'
                            USING ERRCODE = '23514';
                    END IF;
                    RETURN NEW;
                END IF;
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'communication_website_canary_run_immutable'
                        USING ERRCODE = '23514';
                END IF;
                IF OLD.state IS DISTINCT FROM 'armed'
                   OR NEW.state IS DISTINCT FROM 'terminal'
                   OR NEW.run_id IS DISTINCT FROM OLD.run_id
                   OR NEW.event_id IS DISTINCT FROM OLD.event_id
                   OR NEW.event_type IS DISTINCT FROM OLD.event_type
                   OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                   OR NEW.storefront_id IS DISTINCT FROM OLD.storefront_id
                   OR NEW.recipient_key IS DISTINCT FROM OLD.recipient_key
                   OR NEW.armed_control_revision IS DISTINCT FROM OLD.armed_control_revision
                   OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                    RAISE EXCEPTION 'communication_website_canary_run_immutable'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
            $function$ LANGUAGE plpgsql
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER {CANARY_TRIGGER}
            BEFORE INSERT OR UPDATE OR DELETE ON communication_website_canary_run
            FOR EACH ROW EXECUTE FUNCTION {CANARY_FUNCTION}()
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {BACKLOG_FUNCTION}()
            RETURNS trigger AS $function$
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    IF NEW.state IS DISTINCT FROM 'started'
                       OR NEW.outcome_code IS NOT NULL
                       OR NEW.aggregate_counts IS NOT NULL
                       OR NEW.finished_at IS NOT NULL THEN
                        RAISE EXCEPTION 'communication_website_backlog_operation_immutable'
                            USING ERRCODE = '23514';
                    END IF;
                    RETURN NEW;
                END IF;
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'communication_website_backlog_operation_immutable'
                        USING ERRCODE = '23514';
                END IF;
                IF OLD.state IS DISTINCT FROM 'started'
                   OR NEW.state NOT IN ('succeeded', 'blocked', 'failed')
                   OR NEW.operation_id IS DISTINCT FROM OLD.operation_id
                   OR NEW.manifest_fingerprint IS DISTINCT FROM OLD.manifest_fingerprint
                   OR NEW.manifest_summary::text IS DISTINCT FROM OLD.manifest_summary::text
                   OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                    RAISE EXCEPTION 'communication_website_backlog_operation_immutable'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
            $function$ LANGUAGE plpgsql
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER {BACKLOG_TRIGGER}
            BEFORE INSERT OR UPDATE OR DELETE ON communication_website_backlog_operation
            FOR EACH ROW EXECUTE FUNCTION {BACKLOG_FUNCTION}()
            """
        )
    )


def _create_sqlite_immutability_triggers() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER {CANARY_TRIGGER}_insert
            BEFORE INSERT ON communication_website_canary_run
            FOR EACH ROW WHEN NOT (
                NEW.state = 'armed'
                AND NEW.terminal_outcome IS NULL
                AND NEW.terminal_control_revision IS NULL
                AND NEW.finished_at IS NULL
            )
            BEGIN
                SELECT RAISE(ABORT, 'communication_website_canary_run_immutable');
            END
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER {CANARY_TRIGGER}_update
            BEFORE UPDATE ON communication_website_canary_run
            FOR EACH ROW WHEN NOT (
                OLD.state = 'armed' AND NEW.state = 'terminal'
                AND NEW.run_id IS OLD.run_id
                AND NEW.event_id IS OLD.event_id
                AND NEW.event_type IS OLD.event_type
                AND NEW.tenant_id IS OLD.tenant_id
                AND NEW.storefront_id IS OLD.storefront_id
                AND NEW.recipient_key IS OLD.recipient_key
                AND NEW.armed_control_revision IS OLD.armed_control_revision
                AND NEW.created_at IS OLD.created_at
            )
            BEGIN
                SELECT RAISE(ABORT, 'communication_website_canary_run_immutable');
            END
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER {CANARY_TRIGGER}_delete
            BEFORE DELETE ON communication_website_canary_run
            FOR EACH ROW BEGIN
                SELECT RAISE(ABORT, 'communication_website_canary_run_immutable');
            END
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER {BACKLOG_TRIGGER}_insert
            BEFORE INSERT ON communication_website_backlog_operation
            FOR EACH ROW WHEN NOT (
                NEW.state = 'started'
                AND NEW.outcome_code IS NULL
                AND NEW.aggregate_counts IS NULL
                AND NEW.finished_at IS NULL
            )
            BEGIN
                SELECT RAISE(ABORT, 'communication_website_backlog_operation_immutable');
            END
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER {BACKLOG_TRIGGER}_update
            BEFORE UPDATE ON communication_website_backlog_operation
            FOR EACH ROW WHEN NOT (
                OLD.state = 'started'
                AND NEW.state IN ('succeeded', 'blocked', 'failed')
                AND NEW.operation_id IS OLD.operation_id
                AND NEW.manifest_fingerprint IS OLD.manifest_fingerprint
                AND NEW.manifest_summary IS OLD.manifest_summary
                AND NEW.created_at IS OLD.created_at
            )
            BEGIN
                SELECT RAISE(ABORT, 'communication_website_backlog_operation_immutable');
            END
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER {BACKLOG_TRIGGER}_delete
            BEFORE DELETE ON communication_website_backlog_operation
            FOR EACH ROW BEGIN
                SELECT RAISE(ABORT, 'communication_website_backlog_operation_immutable');
            END
            """
        )
    )


def _create_immutability_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        _create_postgresql_immutability_triggers()
    elif dialect == "sqlite":
        _create_sqlite_immutability_triggers()
    else:  # pragma: no cover - production and migration tests are closed above
        raise RuntimeError(f"Unsupported website audit trigger dialect: {dialect}")


def _drop_immutability_triggers() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            sa.text(
                f"DROP TRIGGER {CANARY_TRIGGER} "
                "ON communication_website_canary_run"
            )
        )
        op.execute(sa.text(f"DROP FUNCTION {CANARY_FUNCTION}()"))
        op.execute(
            sa.text(
                f"DROP TRIGGER {BACKLOG_TRIGGER} "
                "ON communication_website_backlog_operation"
            )
        )
        op.execute(sa.text(f"DROP FUNCTION {BACKLOG_FUNCTION}()"))
    elif dialect == "sqlite":
        op.execute(sa.text(f"DROP TRIGGER {CANARY_TRIGGER}_insert"))
        op.execute(sa.text(f"DROP TRIGGER {CANARY_TRIGGER}_update"))
        op.execute(sa.text(f"DROP TRIGGER {CANARY_TRIGGER}_delete"))
        op.execute(sa.text(f"DROP TRIGGER {BACKLOG_TRIGGER}_update"))
        op.execute(sa.text(f"DROP TRIGGER {BACKLOG_TRIGGER}_delete"))
        op.execute(sa.text(f"DROP TRIGGER {BACKLOG_TRIGGER}_insert"))
    else:  # pragma: no cover
        raise RuntimeError(f"Unsupported website audit trigger dialect: {dialect}")


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
    op.create_table(
        "communication_website_backlog_operation",
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("manifest_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("manifest_summary", sa.JSON(), nullable=False),
        sa.Column(
            "state",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'started'"),
        ),
        sa.Column("outcome_code", sa.String(length=100), nullable=True),
        sa.Column("aggregate_counts", sa.JSON(none_as_null=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(operation_id) = 36",
            name="ck_communication_website_backlog_operation_id_valid",
        ),
        sa.CheckConstraint(
            "length(manifest_fingerprint) = 64",
            name="ck_communication_website_backlog_manifest_fingerprint_valid",
        ),
        sa.CheckConstraint(
            "(state = 'started' AND outcome_code IS NULL "
            "AND aggregate_counts IS NULL AND finished_at IS NULL) OR "
            "(state IN ('succeeded', 'blocked', 'failed') "
            "AND outcome_code IS NOT NULL "
            "AND length(trim(outcome_code)) > 0 "
            "AND aggregate_counts IS NOT NULL AND finished_at IS NOT NULL)",
            name="ck_communication_website_backlog_operation_lifecycle_valid",
        ),
        sa.PrimaryKeyConstraint("operation_id"),
    )
    op.create_index(
        "ix_communication_website_backlog_operation_state_created",
        "communication_website_backlog_operation",
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
    _create_immutability_triggers()


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
    _drop_immutability_triggers()
    op.drop_index(
        "ix_communication_website_backlog_operation_state_created",
        table_name="communication_website_backlog_operation",
    )
    op.drop_table("communication_website_backlog_operation")
    op.drop_index(
        "ix_communication_website_canary_run_state_created",
        table_name="communication_website_canary_run",
    )
    op.drop_table("communication_website_canary_run")
