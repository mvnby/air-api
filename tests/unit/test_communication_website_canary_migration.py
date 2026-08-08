from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.config import Config
from alembic.script import ScriptDirectory


REVISION = "ab02c3d4e5f6"
DOWN_REVISION = "aa91c2d4e6f8"
HEAD_REVISION = "f2a3b4c5d6e7"
MIGRATION_PATH = Path(
    "alembic/versions/ab02c3d4e5f6_add_website_canary_runtime_target.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "communication_website_canary_migration",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_previous_schema(connection) -> None:
    metadata = sa.MetaData()
    sa.Table(
        "integration_outbox_event",
        metadata,
        sa.Column("event_id", sa.String(32), primary_key=True),
    )
    sa.Table(
        "communication_runtime_state",
        metadata,
        sa.Column("channel", sa.String(32), primary_key=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("canary_run_id", sa.String(36), nullable=True),
        sa.Column("control_revision", sa.BigInteger(), nullable=False),
        sa.Column(
            "installation_estimate_watermark_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("control_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(connection)


def test_website_canary_migration_precedes_the_additive_catalog_snapshot_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert script.get_heads() == [HEAD_REVISION]
    assert script.get_revision(HEAD_REVISION).down_revision == REVISION
    assert script.get_revision(REVISION).down_revision == DOWN_REVISION


def test_postgresql_migration_defines_append_only_audit_triggers() -> None:
    source = MIGRATION_PATH.read_text()
    canary_function = source.split(
        f"CREATE OR REPLACE FUNCTION {{CANARY_FUNCTION}}()", 1
    )[1].split(
        f"CREATE TRIGGER {{CANARY_TRIGGER}}", 1
    )[0]
    backlog_function = source.split(
        f"CREATE OR REPLACE FUNCTION {{BACKLOG_FUNCTION}}()", 1
    )[1].split(
        f"CREATE TRIGGER {{BACKLOG_TRIGGER}}", 1
    )[0]

    assert (
        "BEFORE INSERT OR UPDATE OR DELETE ON communication_website_canary_run"
        in source
    )
    assert "TG_OP = 'INSERT'" in canary_function
    assert "NEW.state IS DISTINCT FROM 'armed'" in canary_function
    assert "NEW.terminal_outcome IS NOT NULL" in canary_function
    assert "NEW.terminal_control_revision IS NOT NULL" in canary_function
    assert "USING ERRCODE = '23514'" in canary_function
    assert "OLD.state IS DISTINCT FROM 'armed'" in canary_function
    assert "NEW.state IS DISTINCT FROM 'terminal'" in canary_function
    assert "NEW.created_at IS DISTINCT FROM OLD.created_at" in canary_function
    assert (
        "BEFORE INSERT OR UPDATE OR DELETE ON communication_website_backlog_operation"
        in source
    )
    assert "TG_OP = 'INSERT'" in backlog_function
    assert "NEW.state IS DISTINCT FROM 'started'" in backlog_function
    assert "NEW.outcome_code IS NOT NULL" in backlog_function
    assert "OLD.state IS DISTINCT FROM 'started'" in backlog_function
    assert (
        "NEW.manifest_summary::text IS DISTINCT FROM "
        "OLD.manifest_summary::text" in backlog_function
    )


def test_website_canary_migration_upgrades_and_forces_off_on_downgrade() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    migration = _load_migration()
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    event_id = "1" * 32
    run_id = "11111111-1111-4111-8111-111111111111"

    with engine.begin() as connection:
        _create_previous_schema(connection)
        connection.execute(
            sa.text(
                "INSERT INTO integration_outbox_event (event_id) VALUES (:event_id)"
            ),
            {"event_id": event_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO communication_runtime_state ("
                "channel, mode, canary_run_id, control_revision, status, "
                "control_updated_at, created_at, updated_at"
                ") VALUES ('telegram', 'off', NULL, 4, 'disabled', :now, :now, :now)"
            ),
            {"now": now},
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        inspector = sa.inspect(connection)
        assert "communication_website_canary_run" in inspector.get_table_names()
        assert (
            "communication_website_backlog_operation"
            in inspector.get_table_names()
        )
        runtime_columns = {
            column["name"]
            for column in inspector.get_columns("communication_runtime_state")
        }
        assert {"canary_kind", "website_canary_run_id"} <= runtime_columns
        assert not {
            "canary_event_id",
            "canary_event_type",
            "canary_tenant_id",
            "canary_storefront_id",
            "canary_recipient_key",
        } & runtime_columns

        with pytest.raises(
            sa.exc.IntegrityError,
            match="communication_website_canary_run_immutable",
        ):
            connection.execute(
                sa.text(
                    "INSERT INTO communication_website_canary_run ("
                    "run_id, event_id, event_type, tenant_id, storefront_id, "
                    "recipient_key, armed_control_revision, state, "
                    "terminal_outcome, terminal_control_revision, created_at, "
                    "finished_at) VALUES ("
                    ":run_id, :event_id, 'tenant.website.contact_lead.created', "
                    "7, 9, 'staff:12', 5, 'terminal', 'dead', 6, :now, :now)"
                ),
                {
                    "run_id": run_id,
                    "event_id": event_id,
                    "now": now,
                },
            )
        connection.execute(
            sa.text(
                "INSERT INTO communication_website_canary_run ("
                "run_id, event_id, event_type, tenant_id, storefront_id, "
                "recipient_key, armed_control_revision, state, created_at"
                ") VALUES ("
                ":run_id, :event_id, 'tenant.website.contact_lead.created', "
                "7, 9, 'staff:12', 5, 'armed', :now)"
            ),
            {"run_id": run_id, "event_id": event_id, "now": now},
        )
        with pytest.raises(
            sa.exc.IntegrityError,
            match="communication_website_canary_run_immutable",
        ):
            connection.execute(
                sa.text(
                    "UPDATE communication_website_canary_run "
                    "SET recipient_key='staff:13' WHERE run_id=:run_id"
                ),
                {"run_id": run_id},
            )
        connection.execute(
            sa.text(
                "UPDATE communication_website_canary_run SET "
                "state='terminal', terminal_outcome='dead', "
                "terminal_control_revision=6, finished_at=:now "
                "WHERE run_id=:run_id"
            ),
            {"run_id": run_id, "now": now},
        )
        with pytest.raises(
            sa.exc.IntegrityError,
            match="communication_website_canary_run_immutable",
        ):
            connection.execute(
                sa.text(
                    "UPDATE communication_website_canary_run "
                    "SET terminal_outcome='sent' WHERE run_id=:run_id"
                ),
                {"run_id": run_id},
            )
        with pytest.raises(
            sa.exc.IntegrityError,
            match="communication_website_canary_run_immutable",
        ):
            connection.execute(
                sa.text(
                    "DELETE FROM communication_website_canary_run "
                    "WHERE run_id=:run_id"
                ),
                {"run_id": run_id},
            )

        operation_id = "22222222-2222-4222-8222-222222222222"
        with pytest.raises(
            sa.exc.IntegrityError,
            match="communication_website_backlog_operation_immutable",
        ):
            connection.execute(
                sa.text(
                    "INSERT INTO communication_website_backlog_operation ("
                    "operation_id, manifest_fingerprint, manifest_summary, "
                    "state, outcome_code, aggregate_counts, created_at, finished_at"
                    ") VALUES (:operation_id, :fingerprint, :manifest, "
                    "'failed', 'forged', :counts, :now, :now)"
                ),
                {
                    "operation_id": "33333333-3333-4333-8333-333333333333",
                    "fingerprint": "c" * 64,
                    "manifest": json.dumps({"event_types": []}),
                    "counts": json.dumps({"event_types": []}),
                    "now": now,
                },
            )
        connection.execute(
            sa.text(
                "INSERT INTO communication_website_backlog_operation ("
                "operation_id, manifest_fingerprint, manifest_summary, state, "
                "created_at) VALUES (:operation_id, :fingerprint, :manifest, "
                "'started', :now)"
            ),
            {
                "operation_id": operation_id,
                "fingerprint": "a" * 64,
                "manifest": json.dumps({"event_types": []}),
                "now": now,
            },
        )
        with pytest.raises(
            sa.exc.IntegrityError,
            match="communication_website_backlog_operation_immutable",
        ):
            connection.execute(
                sa.text(
                    "UPDATE communication_website_backlog_operation SET "
                    "manifest_fingerprint=:fingerprint "
                    "WHERE operation_id=:operation_id"
                ),
                {"fingerprint": "b" * 64, "operation_id": operation_id},
            )
        connection.execute(
            sa.text(
                "UPDATE communication_website_backlog_operation SET "
                "state='blocked', outcome_code='expected_count_changed', "
                "aggregate_counts=:counts, finished_at=:now "
                "WHERE operation_id=:operation_id"
            ),
            {
                "counts": json.dumps({"event_types": []}),
                "now": now,
                "operation_id": operation_id,
            },
        )
        with pytest.raises(
            sa.exc.IntegrityError,
            match="communication_website_backlog_operation_immutable",
        ):
            connection.execute(
                sa.text(
                    "DELETE FROM communication_website_backlog_operation "
                    "WHERE operation_id=:operation_id"
                ),
                {"operation_id": operation_id},
            )
        connection.execute(
            sa.text(
                "UPDATE communication_runtime_state SET "
                "mode='canary', canary_run_id=:run_id, canary_kind='website', "
                "website_canary_run_id=:run_id, control_revision=5 "
                "WHERE channel='telegram'"
            ),
            {"run_id": run_id},
        )

        migration.downgrade()

        row = connection.execute(
            sa.text(
                "SELECT mode, canary_run_id, control_revision "
                "FROM communication_runtime_state WHERE channel='telegram'"
            )
        ).one()
        assert tuple(row) == ("off", None, 6)
        inspector = sa.inspect(connection)
        assert "communication_website_canary_run" not in inspector.get_table_names()
        assert (
            "communication_website_backlog_operation"
            not in inspector.get_table_names()
        )
        downgraded_columns = {
            column["name"]
            for column in inspector.get_columns("communication_runtime_state")
        }
        assert "canary_kind" not in downgraded_columns
        assert "website_canary_run_id" not in downgraded_columns
